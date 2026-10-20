from dataclasses import dataclass, field
import os
from pathlib import Path
import yaml
from .config import PROJECT


@dataclass(frozen=True)
class AgentConfig:
    profile: str
    provider: str
    model: str
    temperature: float | None
    max_tool_calls: int
    max_provider_calls: int
    max_argument_repairs: int
    max_tool_plan_repairs: int
    minimum_retrieval_score: float
    top_k_evidence: int
    prompt_versions: dict[str, str]
    mock_version: str

    @classmethod
    def load(cls, profile=None, provider=None, path=None):
        path = Path(path or PROJECT / 'configs/agent.yaml')
        raw = yaml.safe_load(path.read_text(encoding='utf-8'))
        selected_profile = profile or raw['active_profile']
        if selected_profile not in raw['profiles']:
            raise ValueError(f'Unknown agent profile: {selected_profile}')
        provider_name = provider or os.getenv('TOMATO_AGENT_PROVIDER') or raw['provider']['name']
        if provider_name in {'openai', 'deepseek'}:
            online = OnlineProviderConfig.load(provider_name, path=path)
            model = online.model
            temperature = online.temperature
        elif provider_name == 'mock':
            model = raw['provider']['model']
            temperature = float(raw['provider'].get('temperature', 0))
        else:
            raise ValueError(f'Unsupported provider: {provider_name}')
        profile_data = raw['profiles'][selected_profile]
        prompts = {k: v for k, v in profile_data.items() if k.endswith('_prompt')}
        prompts['repair_prompt'] = raw['profiles']['repair_prompt']
        prompts['tool_plan_repair_prompt'] = raw['profiles']['tool_plan_repair_prompt']
        return cls(selected_profile, provider_name, model, temperature,
                   int(raw['agent']['max_tool_calls']), int(raw['agent'].get('max_provider_calls', 6)),
                   int(raw['agent']['max_argument_repairs']), int(raw['agent'].get('max_tool_plan_repairs', 1)),
                   float(raw['agent']['minimum_retrieval_score']), int(raw['agent']['top_k_evidence']),
                   prompts, profile_data['mock_version'])


@dataclass(frozen=True)
class OnlineProviderConfig:
    provider: str
    model: str
    api_key: str = field(repr=False)
    api_key_env: str
    base_url: str | None
    credential_source: str
    temperature: float | None
    timeout_seconds: float
    max_retries: int
    max_output_tokens: int
    store: bool
    reasoning_effort: str | None = None
    legacy_model: str | None = None

    @classmethod
    def load(cls, provider=None, path=None):
        path = Path(path or PROJECT / 'configs/agent.yaml')
        raw = yaml.safe_load(path.read_text(encoding='utf-8'))
        provider_name = provider or os.getenv('TOMATO_ONLINE_PROVIDER') or raw['online_provider']['name']
        if provider_name == 'openai':
            online = raw['online_provider']
            api_key_env = online['api_key_env']
            api_key = os.getenv(api_key_env, '')
            model = os.getenv(online['model_env'], '').strip()
            if not model:
                raise ValueError(f"Online model must be configured in {online['model_env']}")
            base_url = os.getenv(online.get('base_url_env', ''), '').strip() or None
            source = 'process_environment' if api_key else 'not_configured'
            legacy_model = None
        elif provider_name == 'deepseek':
            from .providers.credentials import resolve_deepseek_credential
            online = raw['deepseek_provider']
            configured_path = os.getenv(online.get('credential_file_env', ''), '').strip()
            fallback_path = online.get('credential_file')
            credential_file = (Path(configured_path) if configured_path else
                               (path.parent / fallback_path if fallback_path else None))
            resolved = resolve_deepseek_credential(credential_file=credential_file)
            api_key_env = online['api_key_env']
            api_key, model, base_url = resolved.api_key, resolved.model, resolved.base_url
            source, legacy_model = resolved.source, resolved.legacy_model
        else:
            raise ValueError(f'Unsupported online provider: {provider_name}')
        temperature = online.get('temperature')
        return cls(provider=provider_name, model=model, api_key=api_key,
            api_key_env=api_key_env, base_url=base_url, credential_source=source,
            temperature=None if temperature is None else float(temperature),
            timeout_seconds=float(online.get('timeout_seconds', 45)),
            max_retries=int(online.get('max_retries', 2)),
            max_output_tokens=int(online.get('max_output_tokens', 4096)),
            store=bool(online.get('store', False)),
            reasoning_effort=online.get('reasoning_effort'),
            legacy_model=legacy_model)


def build_online_provider(provider_name=None, *, max_total_calls=None,
                          allow_external_tool_data=None):
    """Single construction path for CLI, workflows, and online evaluation."""
    from .providers import DeepSeekProvider, OpenAIProvider, ProviderError, ProviderErrorCode
    config = OnlineProviderConfig.load(provider_name)
    if not config.api_key:
        raise ProviderError(ProviderErrorCode.MISSING_CREDENTIALS,
                            f'{config.api_key_env} is required for online execution')
    common = dict(model=config.model, temperature=config.temperature,
        api_key=config.api_key, base_url=config.base_url,
        timeout_seconds=config.timeout_seconds, max_retries=config.max_retries,
        max_output_tokens=config.max_output_tokens, store=config.store,
        max_total_calls=max_total_calls,
        allow_external_tool_data=(os.getenv('TOMATO_ALLOW_EXTERNAL_TOOL_DATA') == '1'
            if allow_external_tool_data is None else bool(allow_external_tool_data)))
    if config.provider == 'deepseek':
        return DeepSeekProvider(reasoning_effort=config.reasoning_effort, **common)
    return OpenAIProvider(**common)
