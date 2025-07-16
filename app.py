import streamlit as st
import ffmpeg
import openai
import yt_dlp
import os
import json
import bcrypt
import requests
import base64

# --- Constantes e Configurações ---
ADMIN_USERNAME = "israel"
DEFAULT_TEMP_PASSWORD = "senhareset"

# Configurar a chave da API da OpenAI de forma segura
try:
    openai.api_key = st.secrets["OPENAI_API_KEY"]
except KeyError:
    st.error("Chave da API da OpenAI não encontrada. Por favor, adicione sua chave em .streamlit/secrets.toml (local) ou nos segredos do Streamlit Cloud.")
    st.stop()

# --- Configuração do GitHub para persistência ---
try:
    GITHUB_TOKEN = st.secrets["github"]["token"]
    GITHUB_REPO_FULL_NAME = st.secrets["github"]["repo"]
    GITHUB_FILE_PATH = st.secrets["github"]["file_path"]

    GITHUB_REPO_OWNER, GITHUB_REPO_NAME = GITHUB_REPO_FULL_NAME.split("/")
    GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/contents/{GITHUB_FILE_PATH}"
    
    HEADERS = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
    }
except KeyError as e:
    st.error(f"Erro na configuração do GitHub nos segredos: {e}. Certifique-se de que 'github.token', 'github.repo' e 'github.file_path' estejam definidos em .streamlit/secrets.toml.")
    st.stop()

st.set_page_config(layout="wide", page_title="Analisador de Vídeos Inteligente")

# Ocultar o ícone de menu e "Made with Streamlit"
hide_streamlit_style = """
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    </style>
    """
st.markdown(hide_streamlit_style, unsafe_allow_html=True)


# --- Funções de Persistência com GitHub ---

def get_file_from_github():
    """
    Busca o arquivo de usuários do GitHub.
    Retorna (dados_json, sha) se encontrado, ou (None, None) se não.
    """
    try:
        response = requests.get(GITHUB_API_URL, headers=HEADERS)
        response.raise_for_status()
        data = response.json()
        if "content" in data and "sha" in data:
            file_content = base64.b64decode(data['content']).decode('utf-8')
            return json.loads(file_content), data['sha']
        return None, None
    except requests.exceptions.RequestException as e:
        if response.status_code == 404:
            st.info(f"Arquivo '{GITHUB_FILE_PATH}' não encontrado no repositório GitHub. Será criado no primeiro salvamento.")
        else:
            st.error(f"Erro ao buscar arquivo do GitHub: {e}. Status: {response.status_code}, Resposta: {response.text}")
        return None, None
    except json.JSONDecodeError as e:
        st.error(f"Erro ao decodificar JSON do arquivo GitHub: {e}. Conteúdo bruto: {file_content[:200]}...")
        return None, None

def put_file_to_github(content, sha=None, commit_message="Update users.json"):
    """
    Envia o conteúdo do arquivo de usuários para o GitHub.
    Requer o SHA para atualizações.
    """
    encoded_content = base64.b64encode(json.dumps(content, indent=4).encode('utf-8')).decode('utf-8')
    
    payload = {
        "message": commit_message,
        "content": encoded_content
    }
    if sha:
        payload["sha"] = sha
    
    try:
        response = requests.put(GITHUB_API_URL, headers=HEADERS, json=payload)
        response.raise_for_status()
        st.toast("Dados salvos no GitHub!")
        return True
    except requests.exceptions.RequestException as e:
        st.error(f"Erro ao salvar arquivo no GitHub: {e}. Status: {response.status_code}, Resposta: {response.text}")
        return False

# --- Funções de Gerenciamento de Usuários e Autenticação (Modificadas para GitHub) ---

def load_users():
    """Carrega os usuários do GitHub. Se não existir, inicializa e tenta salvar."""
    users_data, sha = get_file_from_github()
    if users_data:
        st.session_state.github_file_sha = sha
        return users_data
    else:
        initial_users = {
            ADMIN_USERNAME: {
                "password_hash": bcrypt.hashpw(DEFAULT_TEMP_PASSWORD.encode('utf-8'), bcrypt.gensalt()).decode('utf-8'),
                "role": "admin",
                "first_login": True,
                "reset_by_admin": False
            }
        }
        if put_file_to_github(initial_users, commit_message="Initial users.json creation"):
            st.success("Arquivo de usuários inicial criado com sucesso no GitHub.")
            _, new_sha = get_file_from_github() 
            st.session_state.github_file_sha = new_sha
            return initial_users
        else:
            st.error("Falha ao criar arquivo de usuários inicial no GitHub. Os dados não serão persistidos.")
            return initial_users

def save_users(users):
    """Salva os usuários no GitHub."""
    current_sha = st.session_state.get("github_file_sha")
    if current_sha:
        if put_file_to_github(users, sha=current_sha):
            _, new_sha = get_file_from_github() 
            st.session_state.github_file_sha = new_sha
            return True
        else:
            return False
    else:
        st.warning("SHA do arquivo não encontrado. Tentando criar o arquivo no GitHub.")
        if put_file_to_github(users, commit_message="Create users.json - fallback"):
            _, new_sha = get_file_from_github() 
            st.session_state.github_file_sha = new_sha
            return True
        return False


def hash_password(password):
    """Gera o hash de uma senha."""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def check_password(password, hashed):
    """Verifica se uma senha corresponde ao hash."""
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

def authenticate_user(username, password):
    """Autentica um usuário."""
    users = load_users()
    if username in users:
        user_data = users[username]
        if check_password(password, user_data["password_hash"]):
            st.session_state.logged_in = True
            st.session_state.username = username
            st.session_state.user_role = user_data["role"]
            st.session_state.first_login = user_data["first_login"]
            st.session_state.is_password_reset_by_admin = user_data.get("reset_by_admin", False)
            
            return True
    return False

def logout_user():
    """Desloga o usuário."""
    st.session_state.logged_in = False
    st.session_state.username = None
    st.session_state.user_role = None
    st.session_state.first_login = None
    st.session_state.is_password_reset_by_admin = False
    st.success("Você foi desconectado.")

def change_password_form(username, is_first_login=False):
    """Formulário para o usuário trocar a senha."""
    st.subheader("Alterar Senha")
    
    if st.session_state.get("is_password_reset_by_admin", False):
        st.warning(f"Você deve ter feito login com a senha temporária '{DEFAULT_TEMP_PASSWORD}'. Por favor, defina uma nova senha forte e segura.")
    elif is_first_login:
        st.warning("Esta é sua primeira conexão. Por favor, defina uma nova senha.")
    
    with st.form("change_password_form"):
        new_password = st.text_input("Nova Senha", type="password")
        confirm_password = st.text_input("Confirmar Nova Senha", type="password")
        submit_change = st.form_submit_button("Alterar Senha")

        if submit_change:
            if new_password and confirm_password:
                if new_password == confirm_password:
                    if len(new_password) < 6:
                        st.error("A nova senha deve ter pelo menos 6 caracteres.")
                    else:
                        users = load_users()
                        users[username]["password_hash"] = hash_password(new_password)
                        users[username]["first_login"] = False
                        users[username]["reset_by_admin"] = False
                        save_users(users)
                        st.success("Senha alterada com sucesso! Você pode continuar.")
                        st.session_state.first_login = False
                        st.session_state.is_password_reset_by_admin = False
                        st.rerun()
                else:
                    st.error("As senhas não coincidem.")
            else:
                st.error("Por favor, preencha todos os campos.")
    
    return None

def admin_page():
    """Página de administração para gerenciar usuários."""
    st.title("Painel de Administração")
    st.subheader("Gerenciar Usuários")

    users = load_users()

    st.write("---")
    st.markdown("### Lista de Usuários")
    users_display = [{"Usuário": u, "Função": d["role"], "Primeiro Login": "Sim" if d["first_login"] else "Não", "Reset por Admin": "Sim" if d.get("reset_by_admin", False) else "Não"} for u, d in users.items()]
    st.table(users_display)
    st.write("---")

    st.markdown("### Criar Novo Usuário")
    with st.form("create_user_form"):
        new_username = st.text_input("Nome de Usuário")
        new_password = st.text_input("Senha Inicial", type="password")
        new_role = st.selectbox("Função", ["normal", "admin"])
        create_user_button = st.form_submit_button("Criar Usuário")

        if create_user_button:
            if new_username in users:
                st.error("Nome de usuário já existe.")
            elif not new_username or not new_password:
                st.error("Nome de usuário e senha não podem estar vazios.")
            else:
                users[new_username] = {
                    "password_hash": hash_password(new_password),
                    "role": new_role,
                    "first_login": True,
                    "reset_by_admin": False
                }
                if save_users(users):
                    st.success(f"Usuário '{new_username}' criado com sucesso! A senha inicial é '{new_password}'.")
                    st.rerun()
                else:
                    st.error("Falha ao salvar o novo usuário no GitHub. Tente novamente.")
                
    st.write("---")

    st.markdown("### Editar ou Excluir Usuário")
    selected_username = st.selectbox("Selecione o Usuário", list(users.keys()))

    if selected_username:
        user_data = users[selected_username]
        st.write(f"Editando usuário: **{selected_username}** (Função atual: {user_data['role']})")

        with st.form("edit_delete_user_form"):
            new_role_edit = st.selectbox("Alterar Função para", ["normal", "admin"], index=0 if user_data["role"] == "normal" else 1)
            reset_password_button = st.form_submit_button("Redefinir Senha (para senha inicial)")
            update_role_button = st.form_submit_button("Atualizar Função")
            delete_user_button = st.form_submit_button("Excluir Usuário", help="Cuidado! A exclusão é permanente.", type="secondary")


            if reset_password_button:
                if selected_username == ADMIN_USERNAME and selected_username == st.session_state.username:
                    st.error("O administrador logado não pode redefinir a própria senha inicial por aqui. Use o formulário de alteração de senha.")
                else:
                    users[selected_username]["password_hash"] = hash_password(DEFAULT_TEMP_PASSWORD)
                    users[selected_username]["first_login"] = True
                    users[selected_username]["reset_by_admin"] = True
                    if save_users(users):
                        st.success(f"Senha de '{selected_username}' redefinida para '{DEFAULT_TEMP_PASSWORD}'. Ele terá que trocá-la no próximo login.")
                        st.rerun()
                    else:
                        st.error("Falha ao redefinir a senha no GitHub. Tente novamente.")


            if update_role_button:
                if selected_username == st.session_state.username and new_role_edit != user_data["role"]:
                    st.warning("Você não pode alterar sua própria função enquanto estiver logado. Peça para outro administrador.")
                else:
                    users[selected_username]["role"] = new_role_edit
                    if save_users(users):
                        st.success(f"Função de '{selected_username}' atualizada para '{new_role_edit}'.")
                        st.rerun()
                    else:
                        st.error("Falha ao atualizar a função no GitHub. Tente novamente.")

            if delete_user_button:
                if selected_username == st.session_state.username:
                    st.error("Você não pode excluir sua própria conta enquanto estiver logado.")
                elif selected_username == ADMIN_USERNAME and len([u for u in users.values() if u['role'] == 'admin']) == 1:
                    st.error("Não é possível excluir o único administrador.")
                else:
                    del users[selected_username]
                    if save_users(users):
                        st.success(f"Usuário '{selected_username}' excluído com sucesso.")
                        st.rerun()
                    else:
                        st.error("Falha ao excluir o usuário no GitHub. Tente novamente.")


# --- Interface Principal do Aplicativo ---

def main_app():
    """Contém a lógica principal do analisador de vídeos e áudios."""
    st.title("🎬 Jarvis - Analisador de Mídia Inteligente")
    st.markdown("""
    Extraia a narrativa, enredo, diálogo ou contexto semântico de vídeos ou áudios
    e faça perguntas sobre o conteúdo!
    """)

    st.header("1. Carregar Mídia Local")
    
    uploaded_video_file = st.file_uploader(
        "Arraste e solte ou clique para enviar um arquivo de vídeo (MP4, AVI, MOV, MKV)",
        type=["mp4", "avi", "mov", "mkv"],
        key="video_uploader"
    )
    st.info("Suporta arquivos de até 200MB no Streamlit Cloud. Para arquivos maiores, use o link ou execute localmente.")

    st.markdown("---")

    uploaded_audio_file = st.file_uploader(
        "Arraste e solte ou clique para enviar um arquivo de áudio (MP3, WAV, M4A)",
        type=["mp3", "wav", "m4a"],
        key="audio_uploader"
    )
    st.info("Suporta arquivos de áudio puro para transcrição e análise.")

    st.markdown("---")

    st.header("2. Ou Cole um Link de Vídeo")
    video_link = st.text_input(
        "Ex: https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        placeholder="https://www.youtube.com/watch?v=..."
    )
    st.info("Suporta YouTube e outras plataformas compatíveis com `yt-dlp`.")

    st.markdown("---")

    if st.button("🚀 Processar Mídia e Analisar Conteúdo", type="primary"):
        media_path = None
        audio_path = "temp_audio.mp3" # Nome padrão para o arquivo de áudio

        if uploaded_audio_file is not None:
            try:
                file_extension = uploaded_audio_file.name.split('.')[-1]
                # Salva o arquivo de áudio diretamente para ser transcrito
                audio_path = f"temp_uploaded_audio_{os.urandom(4).hex()}.{file_extension}"
                with open(audio_path, "wb") as f:
                    f.write(uploaded_audio_file.getbuffer())
                st.success(f"✔️ Áudio '{uploaded_audio_file.name}' carregado localmente!")
                media_path = audio_path # Define media_path como o caminho do áudio para pular a extração
                
            except Exception as e:
                st.error(f"❌ Erro ao carregar o áudio: {e}")
                media_path = None # Garante que não prossiga se o áudio falhar

        elif uploaded_video_file is not None:
            try:
                file_extension = uploaded_video_file.name.split('.')[-1]
                media_path = f"temp_uploaded_video_{os.urandom(4).hex()}.{file_extension}"
                with open(media_path, "wb") as f:
                    f.write(uploaded_video_file.getbuffer())
                st.success(f"✔️ Vídeo '{uploaded_video_file.name}' carregado localmente!")
            except Exception as e:
                st.error(f"❌ Erro ao carregar o vídeo: {e}")
                media_path = None

        elif video_link:
            try:
                with st.spinner("⏳ Baixando vídeo com yt-dlp... isso pode levar um tempo."):
                    ydl_opts = {
                        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                        'outtmpl': 'temp_downloaded_video_%(id)s.%(ext)s',
                        'noplaylist': True,
                        'quiet': True,
                        'no_warnings': True,
                    }
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(video_link, download=True)
                        media_path = ydl.prepare_filename(info) # media_path aqui é o caminho do vídeo baixado
                    st.success(f"✔️ Vídeo baixado com sucesso com yt-dlp!")
            except Exception as e:
                st.error(f"❌ Erro ao baixar vídeo do link com yt-dlp: {e}. Verifique o link e tente novamente.")
                media_path = None

        if media_path:
            # Se o media_path não for um arquivo de áudio diretamente carregado, extrai o áudio
            if uploaded_audio_file is None: # Se não foi um upload de áudio direto
                try:
                    with st.spinner("🎧 Extraindo áudio do vídeo com ffmpeg-python..."):
                        (
                            ffmpeg
                            .input(media_path)
                            .output(audio_path, acodec='libmp3lame')
                            .run(overwrite_output=True, capture_stdout=True, capture_stderr=True)
                        )
                        st.success("✔️ Áudio extraído com sucesso!")
                except ffmpeg.Error as e:
                    st.error(f"❌ Erro ao extrair áudio com ffmpeg-python: {e.stderr.decode()}")
                    st.warning("Certifique-se de que o FFmpeg esteja instalado e acessível no PATH do seu sistema.")
                    if os.path.exists(media_path): os.remove(media_path) # Limpa o vídeo se a extração falhar
                    return # Sai da função se a extração de áudio falhar
                except Exception as e:
                    st.error(f"❌ Ocorreu um erro inesperado durante a extração de áudio: {e}")
                    if os.path.exists(media_path): os.remove(media_path)
                    return

            # Continua com a transcrição e análise, agora que temos o audio_path definido
            if os.path.exists(audio_path):
                try:
                    with st.spinner("✍️ Transcrevendo áudio com Whisper (pode demorar para mídias longas)..."):
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
                        Analise o seguinte diálogo ou descrição de conteúdo de um vídeo/áudio e extraia os seguintes elementos:
                        -   **Narrativa Principal:** Qual é a história central ou o objetivo principal do conteúdo?
                        -   **Enredo/Estrutura:** Descreva a sequência de eventos ou a estrutura lógica do conteúdo.
                        -   **Diálogo Chave:** Cite exemplos de falas importantes que definem o tom ou avançam a história.
                        -   **Contexto Semântico:** Quais são os temas, mensagens ou informações subjacentes? Qual é o propósito do conteúdo?
                        -   **Personagens/Participantes:** Se aplicável, identifique os principais participantes e suas prováveis relações ou papéis.

                        Apresente a análise de forma clara e organizada, utilizando tópicos ou parágrafos.

                        ---
                        Conteúdo da Mídia (Transcrição):
                        {full_transcript}
                        """
                        response_analysis = openai.chat.completions.create(
                            model="gpt-4o",
                            messages=[
                                {"role": "system", "content": "Você é um analista de mídia experiente e detalhista, focado em extrair significado e estrutura."},
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

                except Exception as e:
                    st.error(f"❌ Ocorreu um erro durante o processamento da transcrição ou da análise: {e}")
                finally:
                    if os.path.exists(media_path) and uploaded_audio_file is None: # Só remove o vídeo se foi um vídeo, não o áudio puro
                        os.remove(media_path)
                    if os.path.exists(audio_path):
                        os.remove(audio_path)
            else:
                st.error("❌ Não foi possível encontrar o arquivo de áudio para transcrição.")
        else:
            st.warning("⚠️ Por favor, faça upload de um vídeo, faça upload de um áudio ou forneça um link de vídeo para iniciar.")

    st.markdown("---")

    st.header("3. Faça Perguntas sobre o Conteúdo da Mídia")

    if "full_transcript" in st.session_state and st.session_state["full_transcript"]:
        user_question = st.text_input("Digite sua pergunta sobre o conteúdo (ex: 'Qual é o principal argumento?', 'Quem são os personagens?', 'O que acontece no final?'):")

        if st.button("💬 Obter Resposta", type="secondary"):
            if user_question:
                with st.spinner("🤖 Gerando resposta..."):
                    prompt_qa = f"""
                    Com base no seguinte conteúdo da mídia (transcrição completa) e na análise semântica já realizada,
                    responda à pergunta do usuário. Mantenha a resposta concisa, clara e diretamente relacionada ao conteúdo fornecido.
                    Se a informação não estiver disponível no contexto, indique isso.

                    ---
                    Transcrição Completa da Mídia:
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
                            {"role": "system", "content": "Você é um assistente útil e preciso que responde perguntas sobre o conteúdo de mídias, utilizando a transcrição e análise semântica fornecidas."},
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
        st.info("💡 Processo uma mídia (vídeo ou áudio) primeiro para habilitar a seção de perguntas e respostas.")


# --- Lógica de Roteamento Principal (Autenticação) ---
# Inicializa o estado da sessão se não existir
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "username" not in st.session_state:
    st.session_state.username = None
if "user_role" not in st.session_state:
    st.session_state.user_role = None
if "first_login" not in st.session_state:
    st.session_state.first_login = None
if "is_password_reset_by_admin" not in st.session_state:
    st.session_state.is_password_reset_by_admin = False
# Adicionado para persistência do GitHub
if "github_file_sha" not in st.session_state:
    st.session_state.github_file_sha = None


if st.session_state.logged_in:
    # Lógica para sidebar
    st.sidebar.write(f"Bem-vindo, {st.session_state.username}!")
    st.sidebar.button("Sair", on_click=logout_user)

    if st.session_state.first_login:
        change_password_form(st.session_state.username, is_first_login=True) 
    elif st.session_state.user_role == "admin":
        # Sidebar para administradores
        with st.sidebar:
            st.subheader("Painel de Administração")
            if st.button("Gerenciar Usuários", key="admin_btn"):
                st.session_state.current_page = "admin"
            if st.button("Analisador de Mídias", key="app_btn"):
                st.session_state.current_page = "app"

        # Renderizar a página apropriada
        if "current_page" not in st.session_state or st.session_state.current_page == "app":
            main_app()
        elif st.session_state.current_page == "admin":
            admin_page()

    else: # Usuário normal
        # Sidebar para usuário normal (sem opção de admin)
        with st.sidebar:
            st.subheader("Menu")
            st.write("Você está acessando o Analisador de Mídias.")
        main_app() # Sempre mostra o app principal para usuários normais

else: # Não logado, mostra formulário de login
    st.title("🎬 Jarvis - Analisador de Mídia Inteligente")
    st.header("Faça Login para Continuar")
    st.info(f"Se sua senha foi redefinida por um administrador, use a senha temporária **'{DEFAULT_TEMP_PASSWORD}'** para fazer seu primeiro login e então defina uma nova senha.")

    username = st.text_input("Usuário")
    password = st.text_input("Senha", type="password")
    login_button = st.button("Entrar")

    if login_button:
        if authenticate_user(username, password):
            st.success("Login bem-sucedido!")
            st.rerun()
        else:
            st.error("Usuário ou senha incorretos.")