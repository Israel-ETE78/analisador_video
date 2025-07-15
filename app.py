import streamlit as st # Biblioteca principal para a interface web
import ffmpeg # Para manipulação de vídeo (extração de áudio)
import openai # Para interagir com as APIs da OpenAI (GPT-4o e Whisper)
# from pytube import YouTube # <-- REMOVA/COMENTE esta linha
import yt_dlp # <-- ADICIONE esta linha: Nova biblioteca para baixar vídeos
import os # Para operações de sistema de arquivos (criar/deletar arquivos temporários)
# from pydub import AudioSegment # Já comentada/removida anteriormente, mantenha assim

# Configurar a chave da API da OpenAI de forma segura
try:
    openai.api_key = st.secrets["OPENAI_API_KEY"]
except KeyError:
    st.error("Chave da API da OpenAI não encontrada. Por favor, adicione sua chave em .streamlit/secrets.toml")
    st.stop()

st.set_page_config(layout="wide", page_title="Analisador de Vídeos Inteligente")

st.title("🎬 Jarvis - Analisador de Vídeos Inteligente")
st.markdown("""
Extraia a narrativa, enredo, diálogo ou contexto semântico de vídeos
e faça perguntas sobre o conteúdo!
""")

hide_streamlit_style = """
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    </style>
    """
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

st.header("1. Carregar Vídeo Local")
uploaded_file = st.file_uploader(
    "Arraste e solte ou clique para enviar um arquivo de vídeo (MP4, AVI, MOV, MKV)",
    type=["mp4", "avi", "mov", "mkv"]
)
st.info("Suporta arquivos de até 200MB no Streamlit Cloud. Para arquivos maiores, use o link ou execute localmente.")

st.markdown("---")

st.header("2. Ou Cole um Link de Vídeo")
video_link = st.text_input(
    "Ex: https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    placeholder="https://www.youtube.com/watch?v=..."
)
st.info("Suporta YouTube e outras plataformas compatíveis com `yt-dlp`.")

st.markdown("---")

if st.button("🚀 Processar Vídeo e Analisar Conteúdo", type="primary"):
    video_path = None
    if uploaded_file is not None:
        try:
            file_extension = uploaded_file.name.split('.')[-1]
            # Usar um nome de arquivo único para uploads para evitar conflitos se o Streamlit persistir arquivos
            video_path = f"temp_uploaded_video_{os.urandom(4).hex()}.{file_extension}"
            with open(video_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            st.success(f"✔️ Vídeo '{uploaded_file.name}' carregado localmente!")
        except Exception as e:
            st.error(f"❌ Erro ao carregar o vídeo: {e}")
            video_path = None

    elif video_link: # <--- ESTA É A SEÇÃO QUE SERÁ SUBSTITUÍDA/ALTERADA
        try:
            with st.spinner("⏳ Baixando vídeo com yt-dlp... isso pode levar um tempo."):
                # Opções para yt-dlp
                ydl_opts = {
                    'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best', # Prioriza mp4 com melhor vídeo e áudio
                    'outtmpl': 'temp_downloaded_video_%(id)s.%(ext)s', # Nome de arquivo temporário com ID único
                    'noplaylist': True, # Garante que não baixe playlists
                    'quiet': True, # Suprime a maioria das mensagens de saída
                    'no_warnings': True, # Suprime avisos
                }
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(video_link, download=True)
                    video_path = ydl.prepare_filename(info) # Obtém o caminho do arquivo baixado
                st.success(f"✔️ Vídeo baixado com sucesso com yt-dlp!")
        except Exception as e:
            st.error(f"❌ Erro ao baixar vídeo do link com yt-dlp: {e}. Verifique o link e tente novamente.")
            video_path = None

    if video_path:
        audio_path = "temp_audio.mp3"
        try:
            with st.spinner("🎧 Extraindo áudio do vídeo com ffmpeg-python..."):
                (
                    ffmpeg
                    .input(video_path)
                    .output(audio_path, acodec='libmp3lame')
                    .run(overwrite_output=True, capture_stdout=True, capture_stderr=True)
                )
                st.success("✔️ Áudio extraído com sucesso!")

            with st.spinner("✍️ Transcrevendo áudio com Whisper (pode demorar para vídeos longos)..."):
                with open(audio_path, "rb") as audio_file:
                    transcript = openai.audio.transcriptions.create(
                        model="whisper-1",
                        file=audio_file
                    )
                full_transcript = transcript.text
                st.subheader("📝 Transcrição Completa:")
                st.expander("Clique para ver a transcrição completa").write(full_transcript)
                st.success("✔️ Transcrição concluída!")

            st.subheader("🧠 Análise Semântica (Narrativa, Enredo, Contexto):")
            with st.spinner("🔍 Analisando conteúdo com GPT-4o..."):
                prompt_analysis = f"""
                Analise o seguinte diálogo ou descrição de conteúdo de um vídeo e extraia os seguintes elementos:
                -   **Narrativa Principal:** Qual é a história central ou o objetivo principal do vídeo?
                -   **Enredo/Estrutura:** Descreva a sequência de eventos ou a estrutura lógica do conteúdo.
                -   **Diálogo Chave:** Cite exemplos de falas importantes que definem o tom ou avançam a história.
                -   **Contexto Semântico:** Quais são os temas, mensagens ou informações subjacentes? Qual é o propósito do vídeo?
                -   **Personagens/Participantes:** Se aplicável, identifique os principais participantes e suas prováveis relações ou papéis.

                Apresente a análise de forma clara e organizada, utilizando tópicos ou parágrafos.

                ---
                Conteúdo do Vídeo (Transcrição):
                {full_transcript}
                """
                response_analysis = openai.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": "Você é um analista de vídeo experiente e detalhista, focado em extrair significado e estrutura."},
                        {"role": "user", "content": prompt_analysis}
                    ],
                    temperature=0.7,
                    max_tokens=2000
                )
                analysis_text = response_analysis.choices[0].message.content
                st.write(analysis_text)
                st.success("✔️ Análise semântica concluída!")

                st.session_state["full_transcript"] = full_transcript
                st.session_state["analysis_text"] = analysis_text

        except ffmpeg.Error as e:
            st.error(f"❌ Erro ao extrair áudio com ffmpeg-python: {e.stderr.decode()}")
            st.warning("Certifique-se de que o FFmpeg esteja instalado e acessível no PATH do seu sistema.")
        except Exception as e:
            st.error(f"❌ Ocorreu um erro durante o processamento do vídeo ou da análise: {e}")
        finally:
            if os.path.exists(video_path):
                os.remove(video_path)
            if os.path.exists(audio_path):
                os.remove(audio_path)
    else:
        st.warning("⚠️ Por favor, faça upload de um vídeo ou forneça um link para iniciar.")

st.markdown("---")

st.header("3. Faça Perguntas sobre o Conteúdo do Vídeo")

if "full_transcript" in st.session_state and st.session_state["full_transcript"]:
    user_question = st.text_input("Digite sua pergunta sobre o vídeo (ex: 'Qual é o principal argumento?', 'Quem são os personagens?', 'O que acontece no final?'):")

    if st.button("💬 Obter Resposta", type="secondary"):
        if user_question:
            with st.spinner("🤖 Gerando resposta com GPT-4o..."):
                prompt_qa = f"""
                Com base no seguinte conteúdo do vídeo (transcrição completa) e na análise semântica já realizada,
                responda à pergunta do usuário. Mantenha a resposta concisa, clara e diretamente relacionada ao conteúdo fornecido.
                Se a informação não estiver disponível no contexto, indique isso.

                ---
                Transcrição Completa do Vídeo:
                {st.session_state["full_transcript"]}

                ---
                Análise Semântica Anterior:
                {st.session_state["analysis_text"]}

                ---
                Pergunta do Usuário:
                {user_question}

                Resposta:
                """
                response_qa = openai.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": "Você é um assistente útil e preciso que responde perguntas sobre o conteúdo de vídeos, utilizando a transcrição e análise semântica fornecidas."},
                        {"role": "user", "content": prompt_qa}
                    ],
                    temperature=0.5,
                    max_tokens=700
                )
                st.subheader("💡 Resposta:")
                st.write(response_qa.choices[0].message.content)
        else:
            st.warning("⚠️ Por favor, digite sua pergunta para obter uma resposta.")
else:
    st.info("💡 Processo um vídeo primeiro para habilitar a seção de perguntas e respostas.")