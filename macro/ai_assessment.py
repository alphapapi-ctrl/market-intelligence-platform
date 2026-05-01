"""
macro/ai_assessment.py
======================
Shared AI assessment helper for the dashboard.
Provides get_ai_assessment() and render_ai_assessment().
"""

import requests


def get_ai_assessment(prompt, api_key, model='claude-sonnet-4-6', max_tokens=1500):
    """
    Call Claude API and return (text, error).
    Returns (text, None) on success, (None, error_msg) on failure.
    """
    if not api_key:
        return None, "No API key configured — add in Settings"

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


def render_ai_assessment(prompt, settings, section_key, cached_assessment=None):
    """
    Render AI assessment widget in Streamlit.
    Checks enabled flag, validates API key, shows generate button.
    Returns the assessment text if generated, else None.
    """
    import streamlit as st

    ai_cfg  = settings.get('ai_features', {})
    enabled = ai_cfg.get('enabled', False)
    api_key = ai_cfg.get('api_key', ai_cfg.get('anthropic_api_key', ''))
    model   = ai_cfg.get('model', 'claude-sonnet-4-6')

    if not enabled:
        return None

    if not api_key:
        st.warning("AI features enabled but no API key set — add in Settings")
        return None

    def _render_box(text):
        # Convert newlines to <br> for HTML rendering
        html_text = text.replace('\n', '<br>')
        st.markdown(f"""
            <div style="border-left:3px solid #9b5de5;padding:12px 16px;
                        border-radius:0 8px 8px 0;margin:8px 0;
                        background:rgba(155,93,229,0.05)">
                <div style="color:#9b5de5;font-size:10px;font-weight:bold;
                            letter-spacing:1px;margin-bottom:8px">🤖 AI ASSESSMENT</div>
                <div style="font-size:13px;line-height:1.7;white-space:pre-wrap">{html_text}</div>
            </div>
        """, unsafe_allow_html=True)

    # Show cached assessment if available
    if cached_assessment:
        _render_box(cached_assessment)

    # Generate button
    if st.button("🤖 Generate AI Assessment", key=f"ai_{section_key}"):
        with st.spinner("Generating assessment..."):
            text, error = get_ai_assessment(prompt, api_key, model)
        if error:
            st.error(error)
        elif text:
            _render_box(text)
            return text

    return None