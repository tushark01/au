import streamlit as st

def show_floating_assistant(assistant_text: str, gif_url: str):
    # Use a fixed placeholder (acts like a consistent ID)
    if 'assistant_placeholder' not in st.session_state:
        st.session_state['assistant_placeholder'] = st.empty()

    assistant_placeholder = st.session_state['assistant_placeholder']
    assistant_placeholder.markdown(
        f"""
        <style>
        .gif-float {{
            position: fixed;
            bottom: 20px;
            right: 20px;
            z-index: 9999;
            animation: fadeIn 0.5s ease-in;
        }}
        @keyframes fadeIn {{
            from {{ opacity: 0; }}
            to {{ opacity: 1; }}
        }}
        </style>

        <div style="
            position: fixed;
            bottom: 220px;
            right: 50px;
            z-index: 9999;
            background: #f0f0f0;
            color: #333;
            padding: 10px 14px;
            border-radius: 10px;
            box-shadow: 0 4px 8px rgba(0,0,0,0.1);
            max-width: 220px;
            font-size: 15px;
        ">
            {assistant_text}
            <div style="
                content: '';
                position: absolute;
                bottom: -10px;
                right: 20px;
                width: 0;
                height: 0;
                border-left: 10px solid transparent;
                border-right: 10px solid transparent;
                border-top: 10px solid #f0f0f0;
            "></div>
        </div>

        <div class="gif-float" id="floating-gif">
            <img src="{gif_url}" width="200" alt="Loading GIF">
        </div>
        """,
        unsafe_allow_html=True
    )
