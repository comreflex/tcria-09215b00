# Preparação do TCRIA para uso no ChatGPT GPTs

Este guia prepara o repositório para uso em um GPT customizado no ChatGPT, com integração via **Actions**.

## 1) Subir a API em ambiente público

O GPT precisa acessar uma URL HTTPS pública.

Exemplo local:

```bash
uvicorn api.api:app --host 0.0.0.0 --port 8000
```

Endpoints úteis:

- `GET /health`
- `GET /capabilities`
- `POST /audit`
- `POST /audit/official-pipeline`
- `POST /investigations/full-run`

## 2) Validar o schema OpenAPI

Com a API rodando, valide:

- `http://localhost:8000/openapi.json` (local)
- `https://SEU_DOMINIO/openapi.json` (produção)

Este arquivo é o que será importado em **GPT Builder > Actions > Import from URL**.

## 3) Configurar variáveis de ambiente

Crie `.env` a partir de `.env.example`.

Principais variáveis para produção:

- `TCRIA_ALLOWED_INPUT_ROOTS`: restringe diretórios permitidos para leitura.
- `OPENAI_API_KEY`: obrigatório apenas para endpoints que usam Responses API.

## 4) Configurar o GPT no ChatGPT

No GPT Builder:

1. Abra **Actions**.
2. Clique em **Import from URL**.
3. Informe `https://SEU_DOMINIO/openapi.json`.
4. Revise os endpoints habilitados.
5. Defina instruções do GPT limitando o uso a auditoria e organização documental.

## 5) Boas práticas de operação

- Publicar em ambiente com HTTPS e logs.
- Restringir escopo de diretórios com `TCRIA_ALLOWED_INPUT_ROOTS`.
- Evitar habilitar endpoints não necessários ao caso de uso.
- Testar com payloads pequenos antes de execução em lote.

