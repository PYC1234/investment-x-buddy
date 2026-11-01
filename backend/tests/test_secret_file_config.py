from pathlib import Path
from app.core import config
from app.core.config import Settings


def test_render_mount_candidates_and_local_isolation(monkeypatch,tmp_path):
    monkeypatch.setattr(config,'PROJECT_ROOT',tmp_path/'project')
    monkeypatch.setattr(config,'BACKEND_ROOT',tmp_path/'project'/'backend')
    monkeypatch.delenv('RENDER',raising=False)
    assert config.settings_env_files()==(tmp_path/'project'/'.env',)
    monkeypatch.setenv('RENDER','true')
    paths=config.settings_env_files()
    assert Path('/etc/secrets/.env.render-import') in paths
    assert Path('/etc/secrets/.env') in paths
    assert tmp_path/'project'/'backend'/'.env.render-import' in paths


def test_secret_dotenv_and_environment_precedence(monkeypatch,tmp_path):
    for key in ('DEEPSEEK_API_KEY','DEEPSEEK_BASE_URL','DEEPSEEK_MODEL'):
        monkeypatch.delenv(key,raising=False)
    local=tmp_path/'.env'
    secret=tmp_path/'.env.render-import'
    local.write_text('DEEPSEEK_MODEL="local-model"\n',encoding='utf-8')
    secret.write_text('DEEPSEEK_API_KEY="test-only-key"\nDEEPSEEK_BASE_URL="https://example.test/v1"\nDEEPSEEK_MODEL="secret-model"\n',encoding='utf-8')
    settings=Settings(_env_file=(local,secret))
    assert settings.llm_configured
    assert settings.deepseek_model=='secret-model'
    assert 'test-only-key' not in repr(settings)
    monkeypatch.setenv('DEEPSEEK_MODEL','environment-model')
    assert Settings(_env_file=(local,secret)).deepseek_model=='environment-model'
    assert not Settings(_env_file=None).llm_configured
