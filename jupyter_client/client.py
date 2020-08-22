import json
import re
import time
import uuid
from dataclasses import dataclass
from typing import Optional, List

import aiohttp
import websockets.client


@dataclass
class JupyterError:
    name: str
    value: str
    traceback: Optional[List[str]]


@dataclass
class JupyterResponse:
    status: Optional[str] = None
    stdout: Optional[str] = None
    result: Optional[str] = None
    input: Optional[str] = None
    error: Optional[JupyterError] = None


class JupyterSession:
    base_url: str
    session_id: str
    kernel_id: str
    auth: Optional[aiohttp.BasicAuth] = None
    api_session: aiohttp.ClientSession
    websocket: websockets.client.WebSocketClientProtocol

    def __init__(
        self,
        base_url: str,
        username: Optional[str] = None,
        password: Optional[str] = ''
    ):
        self.base_url = base_url
        if username is not None:
            self.auth = aiohttp.BasicAuth(username, password)
        self.api_session = aiohttp.ClientSession(auth=self.auth)

    async def __aenter__(self):
        await self.connect()
        return self

    async def _wait_until_idle(self):
        data = {}
        while data.get('content', {}).get('execution_state') != 'idle':
            data = json.loads(await self.websocket.recv())

    async def _yield_until_idle(self):
        data = {}
        while data.get('content', {}).get('execution_state') != 'idle':
            data = json.loads(await self.websocket.recv())
            yield data

    async def connect(self) -> None:
        sessions_resp = await self.api_session.post(
            f'{self.base_url}/api/sessions',
            json={
                'notebook': {
                    'path': f'temporary_{int(time.time() * 1000)}.ipynb'
                },
                'kernel': {'id': None, 'name': 'django_extensions'}
            }
        )
        sessions_resp.raise_for_status()
        sessions_data = await sessions_resp.json()
        self.session_id = sessions_data['id']
        self.kernel_id = sessions_data['kernel']['id']
        self.websocket = await websockets.client.connect(
            f"{re.sub(r'^http', 'ws', self.base_url)}/api/kernels/"
            f'{self.kernel_id}/channels?session_id={self.session_id}'
        )
        await self.websocket.send(json.dumps({
            'header': {
                'msg_id': uuid.uuid4().hex.upper(),
                'username': 'username',
                'session': self.session_id,
                'msg_type': 'kernel_info_request',
                'version': '5.0'
            },
            'metadata': {},
            'content': {},
            'buffers': [],
            'parent_header': {},
            'channel': 'shell'
        }))
        await self._wait_until_idle()

    async def execute(self, code: str) -> JupyterResponse:
        await self.websocket.send(json.dumps({
            'header': {
                'msg_id': uuid.uuid4().hex.upper(),
                'username': 'username',
                'session': self.session_id,
                'msg_type': 'execute_request',
                'version': '5.0'
            },
            'metadata': {},
            'content': {
                'code': code,
                'silent': False,
                'store_history': True,
                'user_expressions': {},
                'allow_stdin': False,
                'stop_on_error': True
            },
            'buffers': [],
            'parent_header': {},
            'channel': 'shell'
        }))
        response = JupyterResponse()
        async for m in self._yield_until_idle():
            if m['msg_type'] == 'execute_input':
                response.input = m['content']['code']
            elif m['msg_type'] == 'execute_result':
                response.result = next(iter(
                    m['content']['data'].values()
                ))
            elif m['msg_type'] == 'execute_reply':
                response.status = m['content']['status']
            elif m['msg_type'] == 'stream':
                if m['content']['name'] == 'stdout':
                    response.stdout = m['content']['text']
                if m['content']['name'] == 'stderr':
                    response.stderr = m['content']['text']
            elif m['msg_type'] == 'error':
                response.error = JupyterError(
                    name=m['content']['ename'],
                    value=m['content']['evalue'],
                    traceback=m['content']['traceback']
                )
        return response

    async def close(self):
        if self.websocket:
            await self.websocket.close()
        if self.session_id:
            await self.api_session.delete(
                f'{self.base_url}/api/sessions/{self.session_id}'
            )
        await self.api_session.close()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
