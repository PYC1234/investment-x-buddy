import assert from 'node:assert/strict';
import { test } from 'node:test';

test('anonymous use needs no credentials, renews a stale guest once, and never retries an account anonymously', async () => {
  const originalFetch = globalThis.fetch;
  const originalBase = process.env.NEXT_PUBLIC_API_BASE_URL;
  const originalWindow = Object.getOwnPropertyDescriptor(globalThis, 'window');
  const originalSession = Object.getOwnPropertyDescriptor(globalThis, 'sessionStorage');
  const originalLocal = Object.getOwnPropertyDescriptor(globalThis, 'localStorage');
  const storage = new Map<string, string>();
  const session = {getItem: (key:string)=>storage.get(key)??null, setItem:(key:string,value:string)=>storage.set(key,value), removeItem:(key:string)=>storage.delete(key)};
  process.env.NEXT_PUBLIC_API_BASE_URL = 'https://example.invalid';
  Object.defineProperty(globalThis, 'window', {configurable:true, value:{}});
  Object.defineProperty(globalThis, 'sessionStorage', {configurable:true, value:session});
  Object.defineProperty(globalThis, 'localStorage', {configurable:true, value:{removeItem:()=>{}}});
  const calls:{url:string;init?:RequestInit}[]=[];
  const reply=(body:unknown,status=200)=>new Response(JSON.stringify(body),{status});
  let guests=0;
  globalThis.fetch = async (url,init) => {
    calls.push({url:String(url),init});
    if(String(url).endsWith('/auth/guest')) {
      guests++;
      assert.equal(init?.body,undefined, 'anonymous sessions must never ask for credentials');
      return reply({token:'guest-'+guests,expires:Date.now()/1000+1000,user:{id:'g'+guests,username:null,kind:'guest'}});
    }
    return reply({ok:true});
  };
  try {
    const {identity,privateFetch}=await import('../src/lib/identity');
    await Promise.all([identity(),identity()]);
    assert.equal(guests,1,'parallel first requests share one anonymous session');
    await privateFetch('/api/v1/documents/analyze',{method:'POST',body:'{"save_history":false}'});
    assert.equal((calls.at(-1)?.init?.headers as Record<string,string>).Authorization,'Bearer guest-1');
    globalThis.fetch=async(url,init)=>{
      calls.push({url:String(url),init});
      if(String(url).endsWith('/auth/guest')) {
        guests++;
        return reply({token:'guest-'+guests,expires:Date.now()/1000+1000,user:{id:'g'+guests,username:null,kind:'guest'}});
      }
      return (init?.headers as Record<string,string>).Authorization==='Bearer guest-1'?reply({},401):reply({ok:true});
    };
    assert.equal((await privateFetch('/api/v1/documents/analyze',{method:'POST',body:'{}'})).status,200);
    assert.equal(guests,2);
    session.setItem('xbuddy.identity.v1',JSON.stringify({token:'account',expires:Date.now()/1000+1000,user:{id:'a',username:'user',kind:'account'}}));
    globalThis.fetch=async()=>reply({},401);
    assert.equal((await privateFetch('/api/v1/documents/analyze',{method:'POST',body:'{"save_history":true}'})).status,401);
    assert.equal(guests,2,'account failure must not silently switch identity');
    assert.equal(session.getItem('xbuddy.identity.v1'),null);
  } finally {
    globalThis.fetch=originalFetch;
    if(originalBase===undefined)delete process.env.NEXT_PUBLIC_API_BASE_URL;else process.env.NEXT_PUBLIC_API_BASE_URL=originalBase;
    for(const [name,descriptor] of [['window',originalWindow],['sessionStorage',originalSession],['localStorage',originalLocal]] as const) {
      if(descriptor)Object.defineProperty(globalThis,name,descriptor);else Reflect.deleteProperty(globalThis,name);
    }
  }
});
