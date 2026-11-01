const base = process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, '');
const key = 'xbuddy.identity.v1';
export type Identity = {token:string;expires:number;user:{id:string;username:string|null;kind:'account'|'guest'}};
let pending: Promise<Identity> | null = null;
export function storedIdentity(): Identity | null {
  if(typeof window==='undefined')return null;
  try{const v=JSON.parse(sessionStorage.getItem(key)||'null');return v?.expires>Date.now()/1000?v:null;}catch{return null;}
}
function save(value:Identity){sessionStorage.setItem(key,JSON.stringify(value));localStorage.removeItem('investment-x-buddy.active-run');return value;}
async function auth(path:string,body?:unknown):Promise<Identity>{
  if(!base)throw new Error('服务未配置');
  const r=await fetch(`${base}/api/v1/auth/${path}`,{method:'POST',headers:{'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});
  const value=await r.json();if(!r.ok)throw new Error(value.error?.message||'身份验证失败');return save(value);
}
export async function identity(){
  const current=storedIdentity();if(current)return current;
  if(!pending)pending=auth('guest').finally(()=>{pending=null;});return pending;
}
export const signIn=(username:string,password:string,register:boolean)=>auth(register?'register':'login',{username,password});
export async function privateFetch(path:string,init:RequestInit={}){
  if(!base)throw new Error('服务未配置');
  const current=await identity();
  const send=(session:Identity)=>fetch(`${base}${path}`,{...init,cache:'no-store',headers:{'Content-Type':'application/json',...init.headers,Authorization:`Bearer ${session.token}`}});
  const r=await send(current);
  if(r.status!==401)return r;
  // A restart can invalidate a still-unexpired guest token. Renew it silently,
  // but never turn an authenticated account request into an anonymous write.
  if(storedIdentity()?.token!==current.token)return r;
  sessionStorage.removeItem(key);localStorage.removeItem('investment-x-buddy.active-run');
  if(current.user.kind!=='guest'||init.signal?.aborted||path.startsWith('/api/v1/auth/'))return r;
  return send(await identity());
}
export async function signOut(){const r=await privateFetch('/api/v1/auth/logout',{method:'POST'});if(!r.ok)throw new Error('退出失败，请稍后重试');sessionStorage.removeItem(key);localStorage.removeItem('investment-x-buddy.active-run');}
