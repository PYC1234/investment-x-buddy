"""Opaque, revocable sessions. Ownership is always checked server-side."""
import hashlib
import hmac
import json
import secrets
import sqlite3
import time
from functools import lru_cache
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, SecretStr
from app.core.config import Settings, get_settings
from app.services.store import SQLiteStore

router = APIRouter(prefix='/auth', tags=['identity'])


@lru_cache
def store_for(path: str):
    return SQLiteStore(__import__('pathlib').Path(path))


def auth_store(settings: Settings = Depends(get_settings)):
    return store_for(str(settings.sqlite_path))


def digest(value: str):
    return hashlib.sha256(value.encode()).hexdigest()


def limit(store, key, maximum, seconds=900):
    now = time.time()
    with store.connection() as con:
        con.execute('DELETE FROM auth_limits WHERE expires<?', (now,))
        con.execute('INSERT INTO auth_limits(key,count,expires) VALUES(?,1,?) ON CONFLICT(key) DO UPDATE SET count=count+1', (digest(key), now+seconds))
        count = con.execute('SELECT count FROM auth_limits WHERE key=?', (digest(key),)).fetchone()[0]
    if count > maximum:
        raise HTTPException(429, '请求过于频繁，请稍后再试')


def principal(request: Request, store=Depends(auth_store)):
    header = request.headers.get('authorization', '')
    token = header[7:] if header.startswith('Bearer ') else ''
    if not token or len(token) > 200:
        raise HTTPException(401, '请重新登录或开始匿名体验')
    user = store.fetch_one('SELECT u.*,s.expires FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires>?', (digest(token), time.time()))
    if not user:
        raise HTTPException(401, '会话已失效，请重新登录')
    request.state.user = user
    return user


def account(user=Depends(principal)):
    if user['kind'] != 'account':
        raise HTTPException(403, '登录后才能保存和读取个人历史')
    return user


def public_user(user):
    return {'id': user['id'], 'username': user['username'], 'kind': user['kind']}


def issue(store, user):
    token = secrets.token_urlsafe(32)
    expiry = time.time() + (86400 if user['kind']=='guest' else 7*86400)
    store.execute('INSERT INTO sessions VALUES(?,?,?)', (digest(token), user['id'], expiry))
    return {'token': token, 'expires': expiry, 'user': public_user(user)}


class Credentials(BaseModel):
    username: str = Field(pattern=r'^[A-Za-z0-9_]{3,40}$')
    password: SecretStr = Field(min_length=12, max_length=128)

    def password_value(self):
        value = self.password.get_secret_value()
        if not 12 <= len(value) <= 128:
            raise HTTPException(422, '密码需12–128个字符')
        return value


@router.post('/guest')
def guest(request: Request, store=Depends(auth_store)):
    limit(store, 'guest:'+str(request.client.host), 100, 3600)
    with store.connection() as con:
        con.execute('BEGIN IMMEDIATE')
        old = [row[0] for row in con.execute("SELECT id FROM users WHERE kind='guest' AND NOT EXISTS (SELECT 1 FROM sessions WHERE user_id=users.id AND expires>?) AND NOT EXISTS (SELECT 1 FROM runs r JOIN threads t ON t.id=r.thread_id WHERE t.owner_id=users.id AND r.status IN ('PLANNING','RUNNING','APPROVED')) LIMIT 100", (time.time(),))]
        for owner in old:
            for table in ('tool_calls','events','checkpoints','evidence','tasks'):
                con.execute(f'DELETE FROM {table} WHERE run_id IN (SELECT r.id FROM runs r JOIN threads t ON t.id=r.thread_id WHERE t.owner_id=?)',(owner,))
            con.execute('DELETE FROM runs WHERE thread_id IN (SELECT id FROM threads WHERE owner_id=?)',(owner,))
            con.execute('DELETE FROM memories WHERE thread_id IN (SELECT id FROM threads WHERE owner_id=?)',(owner,))
            con.execute('DELETE FROM threads WHERE owner_id=?',(owner,))
            con.execute('DELETE FROM sessions WHERE user_id=?',(owner,))
            con.execute('DELETE FROM users WHERE id=?',(owner,))
        con.execute('DELETE FROM sessions WHERE expires<?',(time.time(),))
    user = {'id': str(uuid4()), 'username': None, 'kind': 'guest'}
    store.execute('INSERT INTO users(id,kind) VALUES(?,?)', (user['id'], 'guest'))
    return issue(store, user)


@router.post('/register', status_code=201)
def register(body: Credentials, request: Request, store=Depends(auth_store)):
    limit(store, 'register:'+str(request.client.host), 20, 3600)
    password = body.password_value()
    salt = secrets.token_hex(16)
    value = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 600000).hex()
    user = {'id': str(uuid4()), 'username': body.username.lower(), 'kind': 'account'}
    try:
        store.execute('INSERT INTO users(id,username,salt,password_hash,kind) VALUES(?,?,?,?,?)', (user['id'], user['username'], salt, value, 'account'))
    except sqlite3.IntegrityError:
        raise HTTPException(409, '该用户名不可用')
    return issue(store, user)


@router.post('/login')
def login(body: Credentials, request: Request, store=Depends(auth_store)):
    limit(store, 'login:'+str(request.client.host)+':'+body.username.lower(), 15)
    limit(store, 'login-ip:'+str(request.client.host), 100)
    password = body.password_value()
    user = store.fetch_one('SELECT * FROM users WHERE username=? AND kind=?', (body.username.lower(), 'account'))
    salt = user['salt'] if user else '00'*16
    value = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 600000).hex()
    if not user or not hmac.compare_digest(value, user['password_hash']):
        raise HTTPException(401, '用户名或密码错误')
    return issue(store, user)


@router.get('/me')
def me(user=Depends(principal)):
    return public_user(user)


@router.post('/logout')
def logout(request: Request, user=Depends(principal), store=Depends(auth_store)):
    store.execute('DELETE FROM sessions WHERE token_hash=?', (digest(request.headers['authorization'][7:]),))
    return {'ok': True}


class Preferences(BaseModel):
    horizon: str = Field(default='', max_length=100)
    risk: str = Field(default='', max_length=100)
    evidence: bool = True


@router.get('/preferences')
def read_preferences(user=Depends(account)):
    return json.loads(user['preferences'])


@router.put('/preferences')
def save_preferences(body: Preferences, user=Depends(account), store=Depends(auth_store)):
    store.execute('UPDATE users SET preferences=? WHERE id=?', (body.model_dump_json(), user['id']))
    return body.model_dump()


@router.delete('/preferences')
def clear_preferences(user=Depends(account), store=Depends(auth_store)):
    store.execute("UPDATE users SET preferences='{}' WHERE id=?", (user['id'],))
    store.execute('DELETE FROM memories WHERE thread_id IN (SELECT id FROM threads WHERE owner_id=?)', (user['id'],))
    return {'ok': True}


