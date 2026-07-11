"""
macro/ai_assessment.py
======================
Shared AI assessment helper for the dashboard.
Provides get_ai_assessment() and render_ai_assessment().
Supports Anthropic, OpenAI, and Ollama providers.
"""

import requests


def get_ai_assessment(prompt, settings, max_tokens=1500):
    """
    Call AI provider and return (text, error).
    Settings dict should contain provider config from ai_features.
    Also accepts a bare API key string for backwards compatibility.
    """
    # backwards compat: if settings is a string, treat as anthropic api key
    if isinstance(settings, str):
        return _call_anthropic(prompt, settings, 'claude-sonnet-4-6', max_tokens)

    provider = settings.get('provider', 'anthropic')

    if provider == 'ollama':
        url = settings.get('ollama_url', 'http://localhost:11434')
        model = settings.get('ollama_model', 'llama3.1:8b')
        return _call_ollama(prompt, url, model, max_tokens)

    elif provider == 'openai':
        api_key = settings.get('openai_api_key', '')
        model = settings.get('openai_model', 'gpt-4o')
        if not api_key:
            return None, "No OpenAI API key configured — add in Settings"
        return _call_openai(prompt, api_key, model, max_tokens)

    else:
        api_key = settings.get('api_key', settings.get('anthropic_api_key', ''))
        model = settings.get('model', 'claude-sonnet-4-6')
        if not api_key:
            return None, "No Anthropic API key configured — add in Settings"
        return _call_anthropic(prompt, api_key, model, max_tokens)


def _call_anthropic(prompt, api_key, model, max_tokens):
    try:
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key"        : api_key,
                "anthropic-version": "2023-06-01",
                "content-type"     : "application/json",
            },
            json={
                "model"     : model,
                "max_tokens": max_tokens,
                "messages"  : [{"role": "user", "content": prompt}]
            },
            timeout=60
        )
        if response.status_code != 200:
            try:
                err = response.json()
                return None, f"API error {response.status_code}: {err.get('error', {}).get('message', response.text)}"
            except:
                return None, f"API error {response.status_code}: {response.text}"
        data = response.json()
        return data['content'][0]['text'], None
    except requests.exceptions.Timeout:
        return None, "API request timed out"
    except Exception as e:
        return None, f"API error: {str(e)}"


def _call_openai(prompt, api_key, model, max_tokens):
    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type" : "application/json",
            },
            json={
                "model"     : model,
                "max_tokens": max_tokens,
                "messages"  : [{"role": "user", "content": prompt}]
            },
            timeout=60
        )
        if response.status_code != 200:
            try:
                err = response.json()
                return None, f"API error {response.status_code}: {err.get('error', {}).get('message', response.text)}"
            except:
                return None, f"API error {response.status_code}: {response.text}"
        data = response.json()
        return data['choices'][0]['message']['content'], None
    except requests.exceptions.Timeout:
        return None, "API request timed out"
    except Exception as e:
        return None, f"API error: {str(e)}"


def _call_ollama(prompt, url, model, max_tokens):
    try:
        response = requests.post(
            f"{url}/api/chat",
            json={
                'model': model,
                'messages': [{'role': 'user', 'content': prompt}],
                'stream': False,
                # num_ctx set explicitly — Ollama's default (2048) silently
                # truncates these multi-section credit prompts from the front
                'options': {'num_predict': max_tokens, 'num_ctx': 8192},
            },
            timeout=180,
        )
        if response.status_code != 200:
            return None, f"Ollama error {response.status_code}: {response.text}"
        data = response.json()
        return data.get('message', {}).get('content', ''), None
    except requests.exceptions.ConnectionError:
        return None, f"Cannot connect to Ollama at {url} — is it running?"
    except requests.exceptions.Timeout:
        return None, "Ollama request timed out (180s)"
    except Exception as e:
        return None, f"Ollama error: {str(e)}"


def render_ai_assessment(prompt, settings, section_key, cached_assessment=None,
                         max_tokens=1500):
    """
    Render AI assessment widget in Streamlit.
    Checks enabled flag, validates config, shows generate button.
    Returns the assessment text if generated, else None.
    """
    import streamlit as st

    ai_cfg  = settings.get('ai_features', {})
    enabled = ai_cfg.get('enabled', False)
    provider = ai_cfg.get('provider', 'anthropic')

    if not enabled:
        return None

    # validate config based on provider
    if provider == 'anthropic':
        api_key = ai_cfg.get('api_key', ai_cfg.get('anthropic_api_key', ''))
        if not api_key:
            st.warning("AI features enabled but no Anthropic API key set — add in Settings")
            return None
    elif provider == 'openai':
        api_key = ai_cfg.get('openai_api_key', '')
        if not api_key:
            st.warning("AI features enabled but no OpenAI API key set — add in Settings")
            return None
    # ollama doesn't need an API key

    def _render_box(text):
        html_text = text.replace('\n', '<br>')
        if provider == 'ollama':
            border_color = '#22c55e'
            bg_color = 'rgba(34,197,94,0.05)'
            label = f'🤖 AI ASSESSMENT — OLLAMA ({ai_cfg.get("ollama_model", "llama3.1:8b")})'
        elif provider == 'openai':
            border_color = '#22c55e'
            bg_color = 'rgba(34,197,94,0.05)'
            label = '🤖 AI ASSESSMENT — OPENAI'
        else:
            border_color = '#9b5de5'
            bg_color = 'rgba(155,93,229,0.05)'
            label = '🤖 AI ASSESSMENT — CLAUDE'

        st.markdown(f"""
            <div style="border-left:3px solid {border_color};padding:12px 16px;
                        border-radius:0 8px 8px 0;margin:8px 0;
                        background:{bg_color}">
                <div style="color:{border_color};font-size:10px;font-weight:bold;
                            letter-spacing:1px;margin-bottom:8px">{label}</div>
                <div style="font-size:13px;line-height:1.7;white-space:pre-wrap">{html_text}</div>
            </div>
        """, unsafe_allow_html=True)

    if cached_assessment:
        _render_box(cached_assessment)

    if st.button("🤖 Generate AI Assessment", key=f"ai_{section_key}"):
        with st.spinner("Generating assessment..."):
            text, error = get_ai_assessment(prompt, ai_cfg, max_tokens=max_tokens)
        if error:
            st.error(error)
        elif text:
            _render_box(text)
            return text

    return None
