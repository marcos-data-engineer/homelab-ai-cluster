# Arquitetura Unificada: Cluster Distribuído, KVM Stealth, Sincronização e Automação de Sessão (PC & Notebook)

**Data de Atualização:** 10/11/2026  
**Sistema Operacional:** Fedora Workstation 45 (GNOME Shell 51 / Wayland nativo)  
**Usuário Padrão:** `marcos` (UID `1000` em ambos os dispositivos)  
**Propósito:** Guia completo e definitivo de arquitetura, serviços, scripts e configurações para restauração ou replicação do ambiente em hardware novo.

---

## 1. Topologia de Rede e Hardware do Cluster

| Especificação | Nó 1 — PC Principal (`pc`) | Nó 2 — Notebook (`notebook`) |
| :--- | :--- | :--- |
| **Endereço IP Fixo** | `192.168.15.5` | `192.168.15.10` |
| **Interface de Rede** | `enp8s0` (Ethernet Gigabit) | `wlp3s0` (Wi-Fi Mesh Deco em modo *Access Point*) |
| **Gateway / DNS** | `192.168.15.1` (Vivo Fibra) | `192.168.15.1` / `1.1.1.1, 8.8.8.8` |
| **Processador (CPU)** | 12 Threads | 8 Threads |
| **Memória RAM** | 16 GB DDR4 | 20 GB DDR4 |
| **GPU Dedicada** | **AMD Radeon RX 7600 (8 GB VRAM GDDR6)** | **NVIDIA GeForce MX150 (2 GB VRAM)** + Intel UHD 620 |
| **Monitores** | Primário: BenQ 24" (`DP-2`, 1920x1080)<br>Secundário: AOC 23" (`HDMI-A-2`, 1920x1080) | Display Integrado 15.6" (1920x1080) |
| **Webcam / Biometria** | Logitech C922 Pro Stream USB (`/dev/video0`) | Realtek EasyCamera integrada (`/dev/video0`) |
| **Papel no Cluster** | Inferência pesada, Visão, Código complexo, Deskflow Servidor, PostgreSQL / n8n | RAG/Embeddings dedicados (`bge-m3`), Deskflow Cliente, 3ª Tela lateral |

---

## 2. Compartilhamento de Teclado e Mouse em Modo Stealth (Deskflow)

### 2.1. Arquitetura e Decisão Técnica
No GNOME 51 (Wayland), ferramentas como `lan-mouse` ou `synergy` tradicional sofrem perda de ponteiro ou exigem confirmação manual constante de portais de segurança. O **Deskflow (`deskflow-core 1.26.0`)** utiliza `libei` (*Emulated Input Server*) e `libportal` com persistência de token TCP estável na porta `4242`.

* **Binário Executável:** `/home/marcos/.local/bin/deskflow-core`
* **Porta de Rede:** `4242/tcp` (liberada no `firewalld`)
* **Posicionamento Físico e Lógico:**
  * **Notebook:** à **Esquerda (`left`)** do PC.
  * **PC:** à **Direita (`right`)** do Notebook.
* **Atalho de Emergência (Forçar foco de volta ao PC):**
  `Ctrl + Shift + Super + Alt` (`switchToScreen(pc)`)

### 2.2. Configurações do Deskflow

#### No PC (`192.168.15.5` — Servidor):
* **Serviço:** `~/.config/systemd/user/deskflow.service` (`deskflow-core server`)
* **Configuração Geral:** `~/.config/Deskflow/Deskflow.conf`
* **Mapa de Telas (`~/.config/Deskflow/deskflow-server.conf`):**
  ```ini
  section: screens
      pc:
      notebook:
  end

  section: links
      pc:
          left = notebook
      notebook:
          right = pc
  end

  section: options
      relativeMouseMoves = false
      clipboardSharing = false
      keystroke(Control+Shift+Super+Alt) = switchToScreen(pc)
  end
  ```

#### No Notebook (`192.168.15.10` — Cliente):
* **Serviço:** `~/.config/systemd/user/deskflow.service` (`deskflow-core client`)
* **Configuração Geral:** `~/.config/Deskflow/Deskflow.conf` (`remoteHost=192.168.15.5`, `port=4242`)

### 2.3. Auto-Aprovação Transparente do Portal (`auto-accept-input-capture.py`)
No Wayland, o GNOME exige que o usuário aprove a captura remota de entrada ("Capture Input"). Para evitar cliques manuais em todo boot ou reconexão:
* **Script Assistente:** `~/.local/bin/auto-accept-input-capture.py` (usa biblioteca de acessibilidade `Atspi 2.0` para detectar a janela, acionar o switch "Allow Remote Input Capturing" e clicar no botão "Share" em menos de 0.5s).
* **Serviço:** `~/.config/systemd/user/auto-accept-input-capture.service`

---

## 3. Sincronização Bidirecional da Área de Transferência (`lan-clip-sync`)

### 3.1. Superação do Isolamento do GNOME Mutter
O Mutter não implementa `wlr-data-control`, bloqueando ferramentas de monitoramento de clipboard em background. 
O daemon desenvolvido em Python (`~/.local/bin/lan-clip-sync.py`):
1. Conecta-se ao barramento **GTK3 sobre XWayland (`DISPLAY=:0`)**, lendo dinamicamente o cookie mais recente `/run/user/1000/.mutter-Xwaylandauth.*`.
2. Monitora o evento nativo `owner-change` da área de transferência (`Ctrl+C`, seleção ou `PrintScreen`).
3. Calcula o hash `SHA-256` do conteúdo para prevenir loops infinitos e envia o pacote via **SSH criptografado (porta 22)** para a máquina parceira.
4. Suporta textos com codificação UTF-8 e imagens completas (`image/png`) de até 50 MB (prints de tela).
* **Serviço Systemd (Ambas as Máquinas):** `~/.config/systemd/user/lan-clip-sync.service`

---

## 4. Autenticação Biométrica Facial e Desbloqueio Conjunto

### 4.1. Reconhecimento Facial com Howdy 3.0 (Logitech C922 no PC)
* **Instalação no Fedora 45 (Python 3.15):**
  * Como a biblioteca legada `pyv4l2` apresentava incompatibilidade de ABI com Python 3.15 (`longintrepr.h`), instalou-se o `dlib`, `elevate` e `keyboard` via `pip3` e o binário oficial do Howdy 3.0 beta via RPM (`principis/howdy-beta`).
  * Pacote de dados com marcos faciais: `howdy-data` (`shape_predictor_5_face_landmarks.dat`).
* **Configuração (`/etc/howdy/config.ini`):**
  ```ini
  device_path = /dev/video0
  capture_device = opencv
  certainty = 3.5
  timeout = 4
  ```
* **SELinux:** Para permitir que o GDM acesse a câmera `/dev/video0`, o domínio `xdm_t` foi colocado em modo permissivo (`sudo semanage permissive -a xdm_t` ou `SELINUX=permissive` em `/etc/selinux/config`).
* **Integração PAM:**
  * `/etc/pam.d/sudo`: `auth sufficient pam_howdy.so`
  * `/etc/pam.d/password-auth`: `auth sufficient pam_howdy.so` (utilizado pelo GDM tanto no login quanto na tela de bloqueio).
  * `/etc/pam.d/system-auth`: `auth sufficient pam_howdy.so`

### 4.2. Estabilidade de Monitores BenQ/AOC e Bloqueio Sincronizado (`dpms-lock-fix.py`)
Ao pressionar `Super+L`, o GNOME Shell tenta colocar os monitores em modo de economia profunda (`PowerSaveMode=3`), fazendo com que portas DisplayPort e HDMI fiquem piscando e procurando sinal de vídeo em loop.
* **Solução:** `~/.local/bin/dpms-lock-fix.py` (`dpms-lock-fix.service` no PC):
  1. Monitora o barramento D-Bus `org.gnome.Mutter.DisplayConfig` e intercepta qualquer tentativa de mudar `PowerSaveMode != 0`, mantendo os monitores acesos e estáveis.
  2. Escuta sinais de bloqueio de tela (`SessionIsLocked` no `SessionManager` e `Lock`/`Unlock` no `login1`).
  3. **Sincronia Total com o Notebook:** Ao travar o PC com `Super+L`, dispara comando via SSH para bloquear a sessão `seat0` do Notebook. Ao destravar o PC pelo rosto, envia o sinal de unlock imediato para o Notebook.
  4. **Desbloqueio no Boot:** Executa `unlock_notebook()` 3 segundos após o login do PC, garantindo que se o Notebook foi ligado antes, seja destravado imediatamente quando você sentar na frente do PC.

### 4.3. Autologin e Bloqueio Seguro no Notebook
* **Autologin:** Habilitado em `/etc/gdm/custom.conf` (`AutomaticLoginEnable=True`, `AutomaticLogin=marcos`).
* **Bloqueio Automático:** `~/.config/systemd/user/lock-on-boot.service` chama `~/.local/bin/lock-on-boot.sh`, que aguarda o `org.gnome.ScreenSaver` ficar ativo e trava a sessão `seat0` 2 segundos após subir, mantendo o Notebook trancado até o PC liberar.

---

## 5. Gerenciamento de Chaveiro sem Pop-ups (`oo7-daemon` + `systemd-creds`)

### 5.1. Causa Raiz do Problema
No Fedora 45, o daemon de credenciais padrão é o **`oo7-daemon`** (implementação moderna em Rust). Quando o usuário faz login sem digitar senha (via Howdy ou Autologin), o módulo `pam_oo7.so` não recebe senha, mantendo o chaveiro `v1/login.keyring` trancado (`Locked: 1`) e fazendo com que Chrome, Antigravity e GNOME Online Accounts exibam pop-ups de autenticação ou percam sessões.

### 5.2. Solução Definitiva com Criptografia de Hardware
Utilizamos a integração nativa do `systemd >= 258` (`ImportCredential=oo7.keyring-encryption-password`):
1. Uma senha aleatória de alta entropia (32 caracteres) foi gerada e criptografada via:
   ```bash
   systemd-creds encrypt --user --name=oo7.keyring-encryption-password - ~/.config/credstore.encrypted/oo7.keyring-encryption-password
   ```
2. Ao subir a sessão gráfica, o systemd descriptografa a credencial na memória e a entrega diretamente ao `oo7-daemon.service`.
3. O chaveiro `login` é desbloqueado com `Locked: 0` antes mesmo do Chrome ou Antigravity serem executados, eliminando qualquer prompt ou perda de login de contas Google.

---

## 6. Otimização do Antigravity e Cluster Ollama Distribuído

### 6.1. Divisão Estratégica de Modelos

| Dispositivo | Modelo Residente | Tamanho | Função Primária |
| :--- | :--- | :--- | :--- |
| **PC (RX 7600 8 GB VRAM)** | `qwen2.5-coder:7b` | 4.7 GB | Geração de código ultrarrápida 100% em VRAM |
| | `qwen3:8b` | 5.2 GB | Raciocínio geral e conversação técnica |
| | `deepseek-r1:14b-q3` | 7.3 GB | Raciocínio lógico e matemático profundo |
| | `qwen2.5-coder:14b` | 9.0 GB | Refatoração arquitetural pesada |
| | `llama3.2-vision:11b` | 7.8 GB | Análise de imagens, diagramas e OCR |
| **Notebook (MX150 2 GB VRAM)** | `bge-m3:latest` | 1.2 GB | **Motor RAG e Embeddings dedicado** (1024 dimensões) |
| | `qwen3:1.7b` | 1.4 GB | Triagem leve e sumarização rápida |
| | `qwen2.5-coder:3b` / `1.5b` | 1.9 GB / 986 MB | Autocomplete e scripts curtos |

### 6.3. Protocolo Global de Operação e Diretivas MCP (`~/.gemini/GEMINI.md`)

O cluster adota diretivas mandatórias para balanceamento entre os nós locais e o orquestrador em nuvem (Antigravity):

1. **Delegação Primária (MCP Ollama Cluster):**
   * **Nó PC (RX 7600):** Modelo `qwen2.5-coder:7b` mantido residente em VRAM para geração de código, scripts, depuração e formulação técnica (evitando trocas frequentes de contexto de VRAM). Modelo `gemma2:9b` acionado exclusivamente para redações longas e sínteses conceituais.
   * **Nó Notebook (MX150):** Uso dedicado para Embeddings e RAG com `bge-m3:latest`. Raciocínio pesado e geração de código são vetados no Notebook devido às limitações térmicas e de GPU.
2. **Papel do Modelo Antigravity (Nuvem):**
   * **Orquestrador e Executor:** O modelo em nuvem delega a formulação analítica, lógica e geração de código ao `qwen2.5-coder:7b` local via MCP.
   * **Execução Direta no SO:** O modelo em nuvem assume diretamente a execução física dos comandos no terminal (`run_command`), manipulação de containers e aplicação cirúrgica de patches nos arquivos (`replace_file_content` / `write_to_file`).
   * **Edição Direta sem MCP:** Restrita a operações puramente mecânicas sem raciocínio (substituição de valores fixos, renomeação de variáveis pontuais) ou em caso de timeout do endpoint do Ollama.
3. **Restrições de Leitura e Proteção de Quota:**
   * Bloqueio explícito de varredura nos diretórios: `_site/`, `.jekyll-cache/`, `.sass-cache/`, `vendor/`, `node_modules/`, `__pycache__/`, `.venv/`, `.git/` e `dist/`.
   * Prevenção de loops com limite máximo de 2 retentativas consecutivas para comandos com falha.

---

## 7. Organização de Telas e Startup GNOME

* **Extensão GNOME Shell (`startup-fix@marcos`):** Localizada em `~/.local/share/gnome-shell/extensions/startup-fix@marcos/extension.js`.
  * Fecha a tela de "Activities / Overview" logo após o login.
  * No Notebook: garante que o Google Chrome abra maximizado em primeiro plano (`chrome-foreground-launch.sh`).
  * No PC: move automaticamente a janela do `GDrive Sync Monitor` para o monitor secundário (AOC 23" HDMI-A-2) e a maximiza.
* **GDrive Sync Monitor (`~/.local/bin/gdrive-monitor-app.py`):** Aplicação nativa GTK3/VTE sobre Wayland que exibe os logs contínuos em tempo real de `journalctl -u gdrive-sync-gdrive.service` com histórico de 15.000 linhas.

---

## 8. Procedimento de Restauração / Disaster Recovery (Passo a Passo)

Caso seja necessário formatar ou configurar uma máquina nova:

```bash
# 1. Configurar SSH sem senha entre as duas máquinas:
ssh-keygen -t ed25519
ssh-copy-id marcos@192.168.15.10   # (do PC para o Notebook)
ssh-copy-id marcos@192.168.15.5    # (do Notebook para o PC)

# 2. Instalar dependências base no Fedora:
sudo dnf install -y python3-pip git rclone libevdev inih pam-devel vte291 seahorse

# 3. Configurar credencial do chaveiro automático:
mkdir -p ~/.config/credstore.encrypted
PW=$(openssl rand -base64 32)
echo -n "$PW" | systemd-creds encrypt --user --name=oo7.keyring-encryption-password - ~/.config/credstore.encrypted/oo7.keyring-encryption-password

# 4. Instalar Howdy (no PC):
sudo pip3 install --break-system-packages dlib elevate keyboard
RPM_URL=$(dnf repoquery --location howdy --repo="copr:copr.fedorainfracloud.org:principis:howdy-beta" | grep x86_64 | head -n1)
DATA_URL=$(dnf repoquery --location howdy-data --repo="copr:copr.fedorainfracloud.org:principis:howdy-beta" | grep noarch | head -n1)
sudo rpm -ivh --nodeps --nosignature "$RPM_URL" "$DATA_URL"
sudo semanage permissive -a xdm_t
sudo howdy add

# 5. Habilitar os serviços systemd do usuário:
systemctl --user enable --now deskflow.service lan-clip-sync.service dpms-lock-fix.service auto-accept-input-capture.service agy-quota-watch.timer snapserver.service snapclient-pc-box.service snapclient-pc-monitor.service snapcast-volume-sync.service

# No Notebook:
systemctl --user enable --now deskflow.service lan-clip-sync.service snapclient-notebook.service snapcast-nb-sender.service
```

---

## 9. Cluster de Áudio Sincronizado e Equalização Espacial (Home Theater 3.0)

Para transformar os três dispositivos de saída em um sistema de som unificado (Home Theater 3.0), foi implementada uma arquitetura com **Snapcast v0.35.0** (relógio temporal e buffer PCM sincronizados na rede local) combinada com processamento digital de sinal nativo no **PipeWire** (crossover ativo e equalização espacial paramétrica). 

O EasyEffects foi descontinuado e removido da inicialização automática em ambos os nós, pois inseria nós virtuais instáveis e overhead desnecessário frente aos módulos nativos de `filter-chain` do PipeWire.

### 9.1. Topologia Acústica e Calibração

* **Esquerda (Notebook - `notebook_eq`):**
  * Hardware: Alto-falantes internos do Notebook (`alsa_output.pci-0000_00_1f.3.analog-stereo`).
  * Processamento: Crossover passa-altas duplo de 24 dB/oct em 300 Hz (elimina distorção e estalos mecânicos nos cones pequenos) + ganho de presença vocal (+5 dB em 1.4 kHz e 3.4 kHz, +3 dB em 7.5 kHz).
  * Distribuição Espacial: Matriz de mixagem estéreo 85% FL / 15% FR.
  * Ganho de Hardware: `130%` (+6.84 dB no PipeWire) com volume Snapcast calibrado em `100%`.
* **Centro (Caixas PC - `pc_box_eq`):**
  * Hardware: Caixas de som analógicas frontais (`alsa_output.pci-0000_0a_00.6.analog-stereo`).
  * Processamento: Full-range estéreo com reforço de graves (+3 dB em 95 Hz, Q=1.0), atenuação de ressonâncias médias (-1.5 dB em 280 Hz) e clareza acústica (+1.5 dB em 2.4 kHz, +1 dB em 8.5 kHz).
  * Volume Snapcast Calibrado: `35%` (ancoragem central sem abafar os canais laterais).
* **Direita (Monitor AOC - `pc_monitor_eq`):**
  * Hardware: Alto-falante embutido do monitor HDMI secundário (`alsa_output.pci-0000_03_00.1.hdmi-stereo-extra1`).
  * Processamento: Filtro passa-altas de 170 Hz (protege o falante do monitor) + compensação de médios/agudos (+2 dB em 1.8 kHz, +2.5 dB em 4.5 kHz).
  * Distribuição Espacial: Matriz de mixagem estéreo 85% FR / 15% FL.
  * Volume Snapcast Calibrado: `55%`.

### 9.2. Fluxo Bidirecional e Configurações

```
[ PC Apps ] ──────> [ Cluster_Home_Theater (pipe-tunnel) ] ──> /tmp/snapfifo ──┐
                                                                               ├──> [ snapserver (meta:///...) ]
[ Notebook Apps ] ─> [ Cluster_Home_Theater_NB (null-sink) ] ──> pw-cat | socat ─┘                 │
                                                                                                  ├──> snapclient-pc-box (PIPEWIRE_NODE=pc_box_eq)
                                                                                                  ├──> snapclient-pc-monitor (PIPEWIRE_NODE=pc_monitor_eq)
                                                                                                  └──> snapclient-notebook (PIPEWIRE_NODE=notebook_eq)
```

1. **Snapserver PC (`~/.config/snapcast/snapserver.conf`):**
   * Parâmetros de baixa latência e sincronismo temporal: `codec = pcm`, `buffer = 250`, `sampleformat = 48000:16:2`.
   * Meta-Stream: `source = meta:///Cluster_PC/Notebook_Audio?name=Cluster_Home_Theater`.
   * Stream PC: `source = pipe:///tmp/snapfifo?name=Cluster_PC&mode=read`.
   * Stream Notebook: `source = tcp://0.0.0.0:4953?name=Notebook_Audio&mode=server`.
2. **Sink PipeWire no PC (`~/.config/pipewire/pipewire.conf.d/20-snapcast-sink.conf`):**
   * Cria o sink padrão `Cluster_Home_Theater` direcionando o áudio PCM 48kHz/16-bit para `/tmp/snapfifo`.
3. **Filter Chains no PC (`~/.config/pipewire/pipewire.conf.d/30-home-theater-eq.conf`):**
   * Define os nós de DSP `pc_box_eq` e `pc_monitor_eq` com convoluções biquad IIR nativas do PipeWire.
4. **Captura e Envio no Notebook:**
   * Sink Virtual (`~/.config/pipewire/pipewire.conf.d/20-snapcast-forward.conf`): `support.null-audio-sink` nomeado `Cluster_Home_Theater_NB` com `monitor.channel-volumes = true` (garante que volume e mute de apps locais afetem o stream de monitoramento).
   * Filter Chain (`~/.config/pipewire/pipewire.conf.d/30-notebook-eq.conf`): Nó `notebook_eq` aplicando o crossover de 300 Hz e o boost paramétrico.
   * Transmissor (`snapcast-nb-sender.service`): Executa `pw-cat --record --raw -P "stream.capture.sink=true" --format s16 --rate 48000 --channels 2 --target Cluster_Home_Theater_NB - | socat -u STDIN TCP:192.168.15.5:4953` (utiliza `--raw` para prevenir problemas de endianness no PipeWire).
5. **Snapclients:**
   * Utilizam `--player alsa -s pipewire` vinculados via variável de ambiente `PIPEWIRE_NODE` para cada sink virtual equalizado correspondente, eliminando o jitter do backend `pulse`.

### 9.3. Daemon de Sincronização e Controle de Volume (`snapcast-volume-sync.py`)

Localizado em [`~/.local/bin/snapcast-volume-sync.py`](file:///home/marcos/.local/bin/snapcast-volume-sync.py) e gerenciado pelo serviço `snapcast-volume-sync.service` no PC:
* **Unificação de Grupo:** Conecta via JSON-RPC na porta `1705` do Snapserver e assegura que os clientes `pc_box`, `pc_monitor` e `notebook` estejam sempre alocados no mesmo grupo sincronizado com suas razões de volume fixadas (35% / 55% / 100%).
* **Sincronização de Mute e Volume Físico:** Monitora eventos do PipeWire via `pactl subscribe`. Quando o usuário altera o volume mestre ou muta o áudio através das teclas de atalho do teclado ou controle do GNOME no PC, o daemon envia comandos `Group.SetMute` e ajusta os volumes de todos os clientes proporcionalmente no Snapserver, mantendo total controle mesmo quando a fonte em reprodução é originária do Notebook.

---

## 10. Rotinas de Atualização Automática, Containers e Daemons de Boot

### 10.1. Atualizações Automáticas de Software e Modelos LLM
* **Microsoft Visual Studio Code (`update-vscode.timer` & `update-vscode.service` no PC):**
  * Executa diariamente à meia-noite (`00:00`) o comando `dnf upgrade -y code` de forma silenciosa e não interativa.
* **Open WebUI & Containers Docker (`containrrr/watchtower`):**
  * O container `watchtower` roda permanentemente com intervalo de 24 horas (`86400s`), checando e atualizando automaticamente os containers em execução (`ghcr.io/open-webui/open-webui:main` e `docker.n8n.io/n8nio/n8n:latest`).
* **Modelos Ollama (`update-ollama-models.timer` em nível de usuário no PC e Notebook):**
  * **No PC (03:00):** Executa `~/.local/bin/update-ollama-models.sh` para verificar e atualizar os modelos homologados: `gemma2:9b` e `qwen2.5-coder:7b`.
  * **No Notebook (03:30):** Executa `~/.local/bin/update-ollama-models.sh` para verificar e atualizar o modelo dedicado: `bge-m3:latest`.

### 10.2. Containers em Execução no Boot (Docker Restart Policy: `always`)
Todos os containers utilizam `--restart always`, inicializando automaticamente com o daemon `docker.service`:
* **No PC Principal (AMD RX 7600 8GB VRAM / 16GB RAM):**
  * `open-webui` (Porta `8080`): Interface web de IA com conexão de upstream para `host.docker.internal:11434` (Ollama PC) e `192.168.15.10:11434` (Ollama Notebook). Modelo padrão definido para `gemma2:9b` (fluidez instantânea no dia a dia) e `qwen2.5-coder:7b` para programação.
  * `watchtower`: Agente de atualização de imagens Docker.
  * `n8n_dev` (Porta `5678`) e `n8n_postgres` (Porta `5432`): Automação de pipelines e banco de dados relacional persistente.
* **No Notebook (`192.168.15.10` - NVIDIA MX150 2GB VRAM / 20GB RAM):**
  * `open-webui`: Espelho de acesso local na rede.
  * `watchtower`: Agente de atualização contínua.
  * `n8n`: Nó executor satélite.

### 10.3. Daemons de Inicialização e Sincronização (System & User)
* **Google Drive Sync (`gdrive-sync-gdrive.timer` no nível de sistema):**
  * Inicia 5 minutos após o boot (`OnBootSec=5min`) e repete a cada 30 minutos (`OnUnitActiveSec=30min`).
  * Utiliza `rclone bisync /home/marcos/gdrive gdrive:` com limpeza automática de travas órfãs (`*.lck`) antes da execução.
* **Sincronização de Contexto Antigravity (`agy-config-sync.timer` e `.path` no nível de usuário):**
  * Monitora alterações na pasta de configuração do Antigravity no PC e dispara sincronização incremental via SSH para o Notebook a cada 10 minutos.
* **Ollama Daemon (`ollama.service` no nível de sistema):**
  * Habilitado no boot em ambos os nós (`systemctl enable --now ollama.service`).
  * PC: Servidor de inferência rápida em GPU VRAM (`gemma2:9b` e `qwen2.5-coder:7b`).
  * Notebook: Servidor exclusivo de embeddings/RAG em GPU VRAM (`bge-m3:latest`).

### 10.4. Inicialização de Aplicativos e Posicionamento de Janelas (PC)
* **Open WebUI (Firefox):**
  * Entrada: `~/.config/autostart/open-webui-firefox.desktop` executando `firefox --new-window http://localhost:8080`.
  * Posicionamento via extensão GNOME `startup-fix@marcos`: detectado como classe `firefox`, movido para o monitor secundário (AOC 23" / `HDMI-A-2`) e maximizado.
* **GDrive Sync Monitor:**
  * Entrada: `~/.config/autostart/gdrive-monitor.desktop`.
  * Posicionamento via extensão GNOME `startup-fix@marcos`: movido para o monitor secundário (AOC 23") e minimizado na barra de tarefas.
* **Google Antigravity:**
  * Entrada: `~/.config/autostart/antigravity.desktop`.
  * Posicionamento via extensão GNOME `startup-fix@marcos`: mantido no monitor primário (BenQ 24" / `DP-2`), maximizado e focado.

### 10.5. Comandos de Restauração Rápida em Hardware Novo
```bash
# 1. Habilitar timers do sistema:
sudo systemctl enable --now docker.service update-vscode.timer gdrive-sync-gdrive.timer ollama.service

# 2. Subir Open WebUI com upstream clusterizado:
docker run -d \
  -p 8080:8080 \
  --add-host=host.docker.internal:host-gateway \
  -v open-webui:/app/backend/data \
  --name open-webui \
  --restart always \
  -e OLLAMA_BASE_URLS="http://host.docker.internal:11434;http://192.168.15.10:11434" \
  ghcr.io/open-webui/open-webui:main

# 3. Subir Watchtower para atualizações diárias:
docker run -d \
  --name watchtower \
  --restart always \
  -v /var/run/docker.sock:/var/run/docker.sock \
  containrrr/watchtower --interval 86400
```