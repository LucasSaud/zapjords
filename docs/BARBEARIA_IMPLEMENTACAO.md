# Barbearia / AppBarber — implementação e apresentação

Data: 18/11/2026. Base de comparação: commit `2aeb484`. Escopo: demonstração local controlada, conforme o PRD. Esta entrega não comprova operação real de WhatsApp ou integração pela API do AppBarber.

## O que está implementado

| Fluxo | Comportamento |
|---|---|
| Importação AppBarber | CSV ou XLSX, até 5 MB e 5.000 linhas, com mapeamento dos cinco campos. Datas brasileiras/ISO e datas de células Excel. |
| Identificação | Neste recorte, aceita telefones brasileiros (DDI 55), preservando DDD; números incompletos ou internacionais são recusados para revisão. Mesmo final em DDDs distintos não mescla os contatos importados. Conflitos de identidade exigem revisão. |
| Reimportação | Atualiza o contexto da visita mais recente, preserva cadastro, demais variáveis, etiquetas e bloqueios. Mantém a visita válida mais recente entre duplicados do arquivo. Não cria envio. |
| Arquivos | Upload temporário em `backend/var/imports`, fora do diretório público, permissões restritas e limpeza após conclusão ou falha. O caminho público legado `/static/imports` retorna 404. |
| Recuperação | Revisão por dias sem atendimento, serviço e profissional. Exclui bloqueados, descanso, pedidos pendentes, identidade ambígua e data não conferida/inválida. Não consulta reservas futuras no CRM. |
| Campanha | Público revisado pode ser carregado na etapa de destinatários; variáveis do template podem receber nome, primeiro nome, serviço, profissional e data. Conferência da agenda e permissão de contato é explícita. |
| Atendimento | Contexto AppBarber na lateral da conversa, link para a agenda e pedidos de agendar, remarcar ou cancelar. A conclusão exige confirmação manual no CRM, com detalhes persistidos como notas internas. |
| Controles de envio | Lista autorizada em modo demonstração, nova consulta de bloqueio antes do envio e recusa de campanhas interrompidas/encerradas ou destinatários já registrados como enviados. Não substitui garantia transacional de entrega única. |
| Templates | Cache local sem confirmação da Meta recebe status `UNVERIFIED`; não é oferecido como template aprovado para envio. |
| Menu | `VITE_BARBERSHOP_MODE` destaca atendimento, campanhas e contatos. Copiloto e follow-ups automáticos ficam ocultos nesse recorte da interface. |

Os campos AppBarber usam `WebhookLead.variables` e `metadata_payload`; pedidos usam `ChatMessage.meta_data`. Não houve alteração de esquema, migração ou nova dependência. Fluxos legados de vendas permanecem no projeto.

## Executar a demonstração

Requisitos: Python 3.12, Node e dependências do projeto. Não requer Docker, PostgreSQL ou RabbitMQ para este recorte local.

Instalação reproduzível, na raiz:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
npm --prefix frontend ci
.venv/bin/python scripts/run_barbershop_demo.py --port 8000
```

Em outro terminal:

```sh
cd frontend
VITE_BARBERSHOP_MODE=true VITE_SIMULATE_MESSAGING=true npm run dev -- --host 127.0.0.1 --port 5176
```

Nesta máquina já foram instaladas as dependências Python em `/private/tmp/zapjords-dev-venv`; o comando de API equivalente é `/private/tmp/zapjords-dev-venv/bin/python scripts/run_barbershop_demo.py --port 8000`. O ambiente em `/private/tmp` é temporário; para uso duradouro, crie a `.venv` acima.

Abra **http://127.0.0.1:5176**. O login gerado fica em `backend/var/barbershop_demo/access.json`, com permissão 0600; use apenas `email` e `password` no formulário. Não compartilhe o arquivo, que também guarda o segredo da sessão. Os dados ficam em `backend/var/barbershop_demo/demo.db`; não são a base operacional da barbearia e não entram no Git.

O inicializador força simulação, lista de envio vazia, scheduler desligado e conexão somente em localhost. Ele não inicia broker ou workers. A listagem de templates local fornece um modelo identificado como **fictício**, com status `DEMO`, sem alegar aprovação da Meta. Tentar executar/agendar a campanha retorna HTTP 409, explicando que o canal e o worker precisam ser validados. Nenhum envio real foi realizado nesta implementação.

## Roteiro de 10 minutos para o dono

1. Mostre o aviso de demonstração e explique: a agenda permanece no AppBarber; esta etapa importa o relatório e organiza a recepção.
2. Em **Contatos → Importar**, selecione AppBarber e carregue `docs/examples/appbarber_demo.csv`. Confira os cinco campos. Marque a conferência de atendimento realizado apenas por se tratar do exemplo fictício conhecido.
3. Abra o histórico: três linhas válidas. Reimporte para mostrar que não duplica os contatos. Ana e Beto têm o mesmo final de telefone e DDDs diferentes.
4. Em **Contatos → Recuperação de clientes**, revise 30 dias. Na data da implementação são três pessoas; com 60 dias, apenas Beto. Filtros de serviço e profissional usam correspondência do texto completo, ignorando maiúsculas.
5. Em **Disparo em Massa**, selecione `demonstracao_convite_sem_envio`, observe o aviso de modelo fictício e avance para contatos. Revise o público, mapeie `BODY_0` para primeiro nome, confirme a revisão fictícia e carregue a lista. Não apresente isso como envio entregue.
6. Em **Atendimento**, abra Ana. Mostre último atendimento, serviço e profissional. Registre uma solicitação de remarcação com horário antigo e novo. Ela permanece pendente até a conferência na agenda externa.
7. Simule a declaração de conclusão somente com texto prefixado por **DEMONSTRAÇÃO FICTÍCIA**. Reabra a conversa para mostrar a persistência e a anotação privada. Isso não é uma alteração real no AppBarber.
8. Encerre com as dependências para um piloto real e combine os responsáveis pela recepção e pelos acessos.

## Configuração para homologação posterior

| Variável | Uso |
|---|---|
| `VITE_BARBERSHOP_MODE=true` | Menu e formulários da barbearia; também aceita `window._env_.BARBERSHOP_MODE`. |
| `VITE_SIMULATE_MESSAGING=true` | Indicador visual; sozinho não impede o backend de enviar. |
| `WHATSAPP_DEMO_MODE=true` | Restringe os envios aos números da lista autorizada no backend. |
| `WHATSAPP_DEMO_ALLOWLIST=` | Vazia bloqueia todos. Em homologação com canal, preencher somente números de teste autorizados, completos e separados por vírgula. |
| `SIMULATE_MESSAGING` | Simulação já existente; o inicializador local força `true`. |
| `ENABLE_SCHEDULER` | O inicializador local força `false`; não faz agendamento de produção. |

Os exemplos estão em `backend/.env.example` e `frontend/.env.example`. API, workers e scheduler devem receber configurações coerentes quando houver homologação real. Não utilize o inicializador SQLite de demonstração como servidor de produção. Em containers, o diretório privado de importação precisa de volume persistente e permissões adequadas antes de depender de retomadas após recriação.

## Validação e evidências

Resultado final: **63 testes de backend e 32 de frontend aprovados** na seleção executada; build concluído. Foram verificados HTTP 200 da interface, HTTP 401 da API sem autenticação, HTTP 404 do arquivo privado e HTTP 409 da execução de campanha no ambiente de demonstração.

Auditoria pré-commit em 19/11/2026: `scripts/audit_security.py` concluiu com código 0, conforme suas exceções existentes. O `pip-audit` reportou três ocorrências ignoradas pelas regras `PYSEC-2026-1325` e `CVE-2026-85394`; o `npm audit --omit=dev` reportou zero vulnerabilidades. Isso não comprova ausência de vulnerabilidades em todas as dependências. Registro: `validation/barbearia/auditoria-pre-commit.txt`.

O registro nominal de testes fica em `validation/barbearia/testes-backend.txt` e `testes-frontend.txt`, incluindo cada teste e seu resultado. A compilação está em `build.txt`. Os testes novos cobrem importação, reimportação, XLSX, DDD, arquivo privado/limpeza em erro, bloqueio de transporte, confidencialidade das notas, agenda assistida, segmentação, aprovação de templates e interação dos formulários.

Foram percorridos no Chrome headless isolado: login, importação do CSV, histórico concluído, abertura da conversa, criação/conclusão de pedido, revisão de inatividade e preparação da campanha. A API e o SQLite foram consultados para conferir persistência. A chamada de execução da demonstração retornou **409**; nenhuma chamada de envio à Meta foi feita.

Imagens em `validation/barbearia/`: importação, recuperação, atendimento e campanha. O arquivo `fluxo.txt` registra o resultado final do navegador e a conferência do banco. O log de inicialização da API está em `api.txt`.

Limites da validação:

- Executada seleção de testes relacionada às alterações, não toda a suíte do repositório. Há três falhas antigas reproduzidas também no commit base: `test_process_bulk_send_success`, `test_process_bulk_send_blocked` e `test_get_import_results_filtering_and_status_counts`. Evidência em `regressoes-preexistentes.txt`. Os dois primeiros têm mocks incompatíveis com a consulta atual de contagem; o terceiro usa `x_client_id` e acesso por atributos incompatíveis com o contrato atual.
- Testes de nomes receberam telefones explícitos nos mocks para a nova conferência de identidade. O teste do header foi alinhado aos atalhos que o perfil vendedor já possui no código; permissões não foram ampliadas por essa correção de teste.
- Build concluído com aviso preexistente sobre tamanho de bundle. Backend emite avisos de depreciação das bibliotecas e de ciclo de foreign keys no teardown SQLite.
- Docker não está disponível nesta máquina. Nenhum container foi reiniciado; API e frontend nativos foram iniciados/reiniciados e verificados. PostgreSQL, RabbitMQ, worker real, recuperação após falha e webhook real não foram homologados.
- Um primeiro ensaio de importação do ambiente local falhou durante os ajustes; o histórico o conserva. A importação posterior concluiu. Os testes agora isolam os uploads temporários para não colidir com IDs da base de demonstração.

## Tarefas restantes, em ordem

1. **Canal real:** configurar credenciais, número autorizado e template de marketing confirmado pela Meta; provar envio, recebimento, resposta, status e respeito à janela de atendimento. Executar lote mínimo autorizado, com lista de teste no backend.
2. **Ambiente operacional:** subir e validar PostgreSQL, RabbitMQ, worker e scheduler; volumes privados, backup/restauração, credenciais e acesso dos atendentes. Fazer testes sob reinício, erro e reentrega antes de usar clientes reais.
3. **Critérios comerciais:** validar o relatório real do AppBarber, período de inatividade, reservas futuras, permissão de contato, frequência e capacidade diária de resposta. Questões registradas em `BUSINESS_RULES.md`.
4. **Homologação de identidade e isolamento:** revisar todos os caminhos legados que ainda comparam sufixos telefônicos, compartilhamento por projeto e atribuição de responsáveis. Os novos endpoints filtram por barbearia, mas isto não equivale à auditoria de todas as rotas legadas.
5. **Controle de campanha:** testar pausa e bloqueio durante execução real, duplicidade de eventos, concorrência, resultado incerto, retentativa e reprocessamento. A conferência implementada antes do envio não garante entrega exatamente uma vez.
6. **API AppBarber:** obter autorização e documentação técnica, validar permissões e ambientes; só então implementar leitura de agenda, disponibilidade e operações de marcação/cancelamento/remarcação. Nenhum endpoint foi presumido ou automatizado pelo login.
7. **Evolução:** exclusão automática de reservas futuras, retorno confirmado como conversão, dashboard da recepção e novas automações somente após validar o processo humano e a integração.

Para amanhã, a formulação correta é: **“gestão de atendimento e preparação de campanhas, com base importada do AppBarber e agenda conferida pela recepção”**. Não apresentar como sincronização automática do CRM nem como WhatsApp operacional já homologado.
