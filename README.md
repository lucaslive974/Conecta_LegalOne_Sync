# ⚖️ Conecta LegalOne Sync (Enterprise Edition)

Serviço corporativo de sincronização automática, monitoramento processual, geração de relatórios estruturados (**DOCX** e **PDF**) e espelhamento em nuvem privada (**Nextcloud via WebDAV**), com alertas em tempo real e notificações por e-mail (**SMTP**).

---

## 🚀 Fluxo Operacional Diário (07:00 AM)

```
[ Host Linux / Crontab (07:00) ]
               │
               ▼
[ Docker: Bootstrap & SMTP Test ] ──(Falha de Conexão SMTP)──> [ Aborta Inicialização ]
               │ (Sucesso)
               ▼
   [ Autenticação LegalOne ] ──(Falha de Login)──> [ Envia E-mail de Alerta ao ADMIN ]
               │ (Sucesso)
               ▼
   [ Conexão WebDAV Nextcloud ] ──(Falha no Servidor)──> [ Envia E-mail de Alerta ao ADMIN ]
               │ (Sucesso)
               ▼
[ Varredura Incremental de Processos ]
               │
       ┌───────┴────────────────────────┐
       ▼                                ▼
[ Inalterado ]                [ Novo ou com Atualização ]
       │                                │
 (Verifica Cópia Local           (Baixa Andamentos Completos)
 e Espelho no Nextcloud)                │
       │                                ▼
       │                    [ Salva no Banco SQLite ]
       │                                │
       │                                ▼
       │                    [ Gera Relatório DOCX ]
       │                                │
       │                                ▼
       │                    [ Renderiza PDF com LibreOffice ]
       │                                │
       └───────┬────────────────────────┘
               ▼
[ Espelhamento Automático no Nextcloud ] (Recria se foi deletado)
               │
               ▼
[ Envio do Relatório Diário por E-mail para Usuários ]
               │
               ▼
          [ Conclusão ]
```

---

## 📁 Estrutura do Projeto

```text
Conecta_LegalOne_Sync/
├── Dockerfile                  <- Imagem Docker pronta com LibreOffice e Python 3.12
├── docker-compose.yml          <- Orquestração do serviço com volumes de dados persistentes
├── requirements.txt            <- Dependências Python (requests, python-docx, apscheduler, etc.)
├── .env.example                <- Modelo de variáveis de ambiente com documentação detalhada
├── .gitignore                  <- Proteção de senhas, banco local e temporários
├── .venv/                      <- Ambiente virtual Python local
├── data/                       <- Persistência do banco SQLite (historico_processos.db)
├── storage/                    <- Cópia local espelhada dos arquivos DOCX e PDF
├── temp/                       <- Área temporária de renderização
└── source/                     <- Código-fonte modular refatorado
    ├── __init__.py
    ├── config.py               <- Validação e carregamento de variáveis de ambiente
    ├── auth.py                 <- Autenticação Basic Auth e extração de JWT do LegalOne
    ├── client.py               <- Cliente HTTP da API Conecta LegalOne
    ├── database.py             <- Gerenciamento de histórico incremental em SQLite
    ├── document_generator.py   <- Geração de DOCX corporativo e conversão para PDF
    ├── nextcloud_client.py     <- Cliente WebDAV com criação recursiva de pastas e uploads
    ├── notifier.py             <- Teste de bootstrap SMTP, alertas de erro e resumo diário
    ├── sync_service.py         <- Pipeline principal de sincronização e espelhamento
    └── main.py                 <- Ponto de entrada CLI e verificação de inicialização
```

---

## ☁️ O que é necessário para conectar ao Nextcloud interno?

O Nextcloud possui suporte nativo ao protocolo **WebDAV**. Para que a aplicação se conecte e envie os arquivos para a nuvem da sua empresa, são necessários apenas 4 parâmetros:

1. **`NEXTCLOUD_URL`**: O endereço do seu Nextcloud interno (ex: `https://nextcloud.empresa.local` ou `http://192.168.1.100:8080`).
2. **`NEXTCLOUD_USER`**: O nome de usuário do Nextcloud da conta de serviço ou do responsável.
3. **`NEXTCLOUD_PASSWORD`**: Recomenda-se gerar uma **Senha de Aplicativo (App Password)**:
   - No Nextcloud, clique na foto do seu perfil -> **Configurações Pessoais**;
   - No menu lateral esquerdo, clique em **Segurança**;
   - Role até a seção **Dispositivos e Sessões**;
   - Digite um nome (ex: `LegalOne_Sync`) e clique em **Criar nova senha de app**;
   - Copie a senha gerada e cole no `NEXTCLOUD_PASSWORD`. *(Isso evita expirar caso você troque sua senha pessoal ou tenha 2FA ativo)*.
4. **`NEXTCLOUD_VERIFY_SSL`**:
   - Caso seu Nextcloud interno utilize certificado autoassinado ou autoridade interna (CA interna), defina como `false` para evitar rejeição por SSL.

---

## 📧 Validações Obrigatórias de Bootstrap (SMTP & Nextcloud)

Na inicialização da aplicação, o sistema **obrigatoriamente valida a conexão com o SMTP e com o Nextcloud ANTES de qualquer requisição ao LegalOne**:
1. **Teste de SMTP**: Se o servidor de e-mail não responder ou a autenticação falhar, a aplicação aborta imediatamente para não rodar sem capacidade de alertas.
2. **Teste de Nextcloud WebDAV**: Se a URL ou as credenciais do Nextcloud falharem, um e-mail de alerta crítico é enviado imediatamente ao `ADMIN_EMAIL` e a aplicação aborta antes de consultar a API ou fazer qualquer raspagem.

---

## 🛠️ Configuração Passo a Passo

### 1. Crie o arquivo `.env`
Copie o exemplo e preencha com suas credenciais reais:
```bash
cp .env.example .env
nano .env
```

### 2. Valide as conexões individualmente
Você pode testar cada serviço isoladamente via terminal:
```bash
# Valida o SMTP
./.venv/bin/legalone-sync --test-smtp

# Valida o Nextcloud
./.venv/bin/legalone-sync --test-nextcloud
```

---

## 🐳 Execução em Produção via Docker & Cron

A aplicação foi projetada para o padrão **run-and-exit** (executa a rotina diária e finaliza o contêiner), ideal para ser disparado pelo cron do Linux.

### Construir a imagem Docker
```bash
docker compose build
```

### Executar manualmente para teste
```bash
docker compose run --rm legalone-sync
```

### Agendar no Cron do Linux (Todo dia às 07:00 AM)
Edite a crontab do servidor:
```bash
crontab -e
```
Adicione a seguinte linha:
```cron
0 7 * * * cd /caminho/completo/Conecta_LegalOne_Sync && docker compose run --rm legalone-sync >> /var/log/legalone_sync.log 2>&1
```

---

## 🛡️ Resiliência e Espelhamento

1. **Cópia Local de Segurança**:
   - Todos os relatórios gerados em DOCX e PDF ficam salvos permanentemente na pasta `./storage/Processos/` no host.
2. **Auto-recriação no Nextcloud**:
   - Caso algum usuário acidentalmente delete a pasta ou arquivo no Nextcloud, no dia seguinte o sincronizador detecta a ausência remota e reenvia automaticamente a cópia local.
3. **Notificação de Incidentes**:
   - Falha de senha/login no LegalOne -> Alerta imediato no e-mail do `ADMIN_EMAIL`.
   - Falha de conexão/permissão no Nextcloud -> Alerta imediato no e-mail do `ADMIN_EMAIL`.
   - Sucesso diário -> Relatório executivo por e-mail com KPIs e lista dos últimos andamentos para os e-mails em `NOTIFICATION_EMAILS`.
