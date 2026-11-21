# agent-causal-diagnosis

[English](#english) | [Português](#português)

---

## English

Pinpoint the exact step that caused an LLM agent to give a wrong answer, prove it by replaying the execution with that single step fixed, and block the same regression from returning in CI.

Standard tracing tools show what an agent did, not why it broke. Across a run with ten tool calls and a couple of sub-agents, the wrong answer usually surfaces at the final step even though the real cause happened much earlier: a tool returned stale data at step two, the model reasoned coherently on top of it for four steps, and the mistake only became visible at step eight. A dashboard can highlight the bad output, yet it cannot tell you which upstream decision to fix or whether fixing it would actually change the outcome.

This repository implements a compact, end-to-end solution for both questions. It includes a customer support agent instrumented with OpenTelemetry, five controlled faults modeled on real production failures, a graph-based diagnosis engine that ranks candidate root causes from spans alone, a counterfactual replay loop that only confirms a cause when patching it produces the right answer, and a CI gate that fails the build if a prompt or configuration change reintroduces a known failure.

### What is inside

The agent runs a decision loop over four tools: order lookup, policy search across a small index, return deadline calculation, and ticket escalation. Every decision and tool call emits an OpenTelemetry span recording its inputs, outputs, and upstream step dependencies. Those dependency links are what make causal tracing possible.

Faults are injected strictly at the boundary between the agent and its environment. There are five failure modes, each based on issues seen in real support pipelines: a stale policy document, a tool returning an HTTP-style success status with an error payload inside, a corrupted order identifier, truncated retrieval context, and a drifting prompt. The tools and planner stay clean, and the diagnosis module never gets told which fault was injected.

During diagnosis, the engine builds a directed dependency graph from the raw spans, scores each upstream step using anomaly detectors, and ranks the suspect steps. Because it reads only OpenTelemetry spans, it works on any trace matching the same schema. Next, the counterfactual step replays the top candidates using a known-good correction for that single step, confirming a root cause only if the patched run produces the expected answer.

Finally, the regression gate runs the full scenario suite under a reference setup and a candidate setup, failing the build if the candidate breaks any case the reference handles properly or misclassifies a fault-free request.

### Quickstart

```bash
git clone [https://github.com/eduardawanderlley/agent-causal-diagnosis.git](https://github.com/eduardawanderlley/agent-causal-diagnosis.git)
cd agent-causal-diagnosis
python -m venv .venv && source .venv/bin/activate
make install      # installs the package and dev dependencies
make test         # runs unit tests for agent behavior, localization, metrics, and gate
make benchmark    # runs all 210 scenarios and writes results to benchmarks/results/
make gate         # runs the CI regression gate against the reference configuration
```

Run a single request with and without the drifted prompt:

```bash
python -m support_agent "Can I still return PED-1004?"
python -m support_agent "Can I still return PED-1004?" --fault prompt_drift
```

The reference agent answers `eligible`, whereas the drifted run answers `not_eligible`. Since the order was delivered 18 days ago and electronics have a 30-day return window, the second answer is wrong. Inspecting the trace reveals why: the drifted prompt skipped the deadline calculation tool and assumed a hardcoded 15-day window.

### Benchmark results

The benchmark evaluates 210 scenarios built from 7 orders, 5 query phrasings, and 6 fault settings. Out of those, 115 runs end with an incorrect outcome (either a wrong final answer or an unnecessary escalation). Each failed run is diagnosed from its spans and verified via counterfactual replay.

| Method | Hit@1 | Hit@3 | MRR |
| :--- | ---: | ---: | ---: |
| First visible error (naive baseline) | 0.000 | 0.522 | 0.376 |
| Nearest steps before the answer (naive baseline) | 0.000 | 0.652 | 0.300 |
| Structural heuristic | 1.000 | 1.000 | 1.000 |
| Heuristic plus counterfactual confirmation | 1.000 | 1.000 | 1.000 |

The full breakdown, including pass rates per fault type, lives in `benchmarks/results/summary.md`.

These numbers deserve honest context. The structural heuristic scores 1.000 here largely because each injected fault leaves a distinct signature that the signal library was written to catch. That proves the end-to-end pipeline works, not that the heuristic generalizes to unseen failure modes, which is the very next thing to test. Similarly, counterfactual replay confirmed the top candidate in every failure, so it did not alter the ranking on this benchmark; its real purpose is filtering out false positives whenever the heuristic guesses wrong.

Triage behavior matters just as much as root-cause localization. Among the 115 failed runs, 90 escalated safely to a human agent, while 25 returned a confident wrong answer (all caused by stale documents or prompt drift). The CI gate exists specifically to catch that second group: any change that quietly shifts failures from safe escalations into confident wrong answers is a serious regression even if overall pass rates look stable.

### How the diagnosis works

The complete methodology is documented in [docs/methodology.md](docs/methodology.md). In short, starting from the step that produced the wrong answer, the engine walks backward along the dependency edges. At every upstream step, it runs a set of anomaly detectors. A stale document timestamp, an error payload wrapped in a success status, an identifier missing from both the user prompt and retrieved evidence, or a final verdict issued without calling the deadline calculator each add weight to that step. Suspects are ranked by total weight, breaking ties in favor of earlier steps since an earlier fault explains more downstream behavior.

To turn a hypothesis into proof, the system takes the top three candidates and replays the exact same input while injecting a ground-truth correction for that one step. If the replayed run outputs the right answer, that step is confirmed as the root cause; otherwise, it gets demoted.

### Connecting to Langfuse and LangSmith

The agent has no direct SDK coupling to either observability platform. Instead, it exports standard OTLP traces to an OpenTelemetry Collector, which fans the telemetry out to both backends simultaneously.

```bash
cp deploy/.env.example deploy/.env      # add your platform keys
set -a; source deploy/.env; set +a
docker run --rm -p 4318:4318 \
  --env-file deploy/.env \
  -v "$(pwd)/deploy/otel-collector.yaml:/etc/otelcol-contrib/config.yaml" \
  otel/opentelemetry-collector-contrib:latest

pip install -e ".[otlp]"
python -m support_agent "Can I still return PED-1004?"
```

Verify the exact OTLP endpoint paths and authentication headers in the Langfuse and LangSmith documentation before deploying, as both vendors occasionally update their ingestion formats.

### Project layout

```text
src/
  support_agent/        agent loop, tools, planner, fault injection, scenarios
    agent.py            decision loop emitting one span per decision and tool call
    planner.py          rule-based planner standing in for the LLM decision step
    faults.py           controlled faults applied at the environment boundary
    interventions.py    known-good corrections used during counterfactual replay
    scenarios.py        the 210-scenario benchmark suite and ground truth labels
    evaluation.py       shared execution, replay, and gate helpers
  causal_diagnosis/     reads spans only; completely decoupled from the agent
    graph.py            builds dependency graphs from raw OpenTelemetry spans
    signals.py          anomaly detectors and signal weights
    localize.py         candidate ranking, baselines, and diagnose() entrypoint
    counterfactual.py   replay-based root-cause confirmation
    metrics.py          Hit@k and MRR evaluation metrics
tests/                  tests for agent behavior, localization, and gate logic
benchmarks/             benchmark runner and committed result summaries
scripts/                CI regression gate script
deploy/                 OpenTelemetry Collector config and environment template
docs/                   architecture notes and methodology details
```

### Limitations

* **Synthetic fault coverage:** The five faults were written manually, so they reflect known failure patterns rather than the messy, overlapping failures that happen in live traffic.
* **Rule-based planner:** Keeping the planner rule-based makes runs fast, free, and deterministic. Using a live LLM planner makes counterfactual replay trickier because you must replay recorded model outputs up to the patched step instead of re-running the planner from scratch (covered in the methodology doc, not implemented yet).
* **Verifier dependency:** Counterfactual confirmation requires an oracle that knows whether the patched answer is right. In this benchmark, ground-truth labels act as the oracle; in production, you need deterministic business-rule checks against source data or curated expectations, otherwise the system falls back to the heuristic ranking.
* **No span-level LLM judge or UI yet:** The structural heuristic serves as the baseline that an LLM judge will need to beat in a future iteration. There is also no web dashboard yet, though the benchmark already tracks core operational metrics like escalation rate, cost per task, and p95 latency.

### Roadmap

* Swap in an LLM-backed planner with recorded trace replay so counterfactual confirmation works on non-deterministic model runs.
* Add unseen fault categories that the current detectors were not explicitly tuned for, measuring true out-of-distribution generalization.
* Implement a span-level LLM judge calibrated against human labels using Cohen's kappa.

### License

MIT. See [LICENSE](LICENSE).

---

## Português

Encontre o passo exato que fez um agente de LLM dar uma resposta errada, comprove a causa reexecutando o fluxo com apenas esse passo corrigido e bloqueie a volta da mesma regressão no CI.

Ferramentas comuns de tracing mostram o que o agente fez, mas não o que causou o erro. Em uma execução com dez chamadas de ferramentas e alguns subagentes, a falha costuma aparecer na última etapa mesmo tendo começado bem antes: uma ferramenta devolveu dados desatualizados no segundo passo, o modelo raciocinou corretamente em cima deles por quatro passos e a resposta errada só surgiu no oitavo. Um dashboard mostra que a resposta final está errada, mas não diz qual decisão precisa mudar nem se corrigi-la resolveria o problema.

Este repositório traz uma implementação completa e enxuta para responder às duas perguntas. Ele reúne um agente de suporte instrumentado com OpenTelemetry, cinco falhas controladas baseadas em problemas reais de produção, um motor de diagnóstico que ranqueia causas prováveis olhando apenas para os spans, uma etapa de replay contrafactual que só confirma uma causa quando a correção faz a resposta acertar, e um gate de regressão que reprova o build se uma mudança de prompt ou modelo reintroduzir uma falha conhecida.

### O que está no projeto

O agente roda um loop de decisão com quatro ferramentas: consulta de pedidos, busca em políticas internas, cálculo de prazo de devolução e abertura de escalonamento humano. Cada decisão e cada chamada de ferramenta gera um span OpenTelemetry registrando entradas, saídas e de quais passos anteriores aquela etapa dependeu. São essas dependências que tornam a análise causal possível.

As falhas são injetadas na fronteira entre o agente e o ambiente. Existem cinco cenários inspirados em incidentes reais de atendimento: documento de política desatualizado, ferramenta que retorna status de sucesso escondendo um erro no payload, identificador de pedido corrompido, contexto de busca truncado e prompt que sofreu drift. As ferramentas e o planner permanecem limpos, e o módulo de diagnóstico nunca sabe qual falha foi ativada.

Na etapa de diagnóstico, o sistema monta um grafo de dependências a partir dos spans, pontua cada etapa anterior usando detectores de anomalias e ordena os candidatos. Como lê apenas spans, funciona sobre qualquer trace que siga o mesmo esquema. Em seguida, o replay contrafactual reexecuta os principais candidatos aplicando uma correção conhecida apenas naquele passo, confirmando a causa raiz somente se a nova execução gerar a resposta certa.

Por fim, o gate de regressão roda toda a suíte de cenários em uma configuração de referência e em uma candidata, falhando o build se a candidata quebrar algum caso que a referência acertava ou errar um cenário sem falhas.

### Como rodar

```bash
git clone [https://github.com/eduardawanderlley/agent-causal-diagnosis.git](https://github.com/eduardawanderlley/agent-causal-diagnosis.git)
cd agent-causal-diagnosis
python -m venv .venv && source .venv/bin/activate
make install      # instala o pacote e as dependências de desenvolvimento
make test         # roda testes de comportamento, localização, métricas e gate
make benchmark    # executa os 210 cenários e salva em benchmarks/results/
make gate         # roda o gate de CI contra a configuração de referência
```

Para testar uma consulta única, com e sem o prompt alterado:

```bash
python -m support_agent "Can I still return PED-1004?"
python -m support_agent "Can I still return PED-1004?" --fault prompt_drift
```

O agente de referência responde `eligible`, enquanto a versão com drift responde `not_eligible`. Como o pedido foi entregue há 18 dias e o prazo para eletrônicos é de 30 dias, a segunda resposta está errada. O trace mostra o motivo: o prompt alterado pulou a ferramenta de cálculo de prazo e raciocinou assumindo uma janela fixa de 15 dias.

### Resultados

O benchmark executa 210 cenários formados por 7 pedidos, 5 variações de pergunta e 6 configurações de falha. Desse total, 115 execuções terminam com resultado incorreto (resposta errada ou escalonamento indevido). Cada falha é diagnosticada pelos spans e validada por replay.

| Método | Hit@1 | Hit@3 | MRR |
| :--- | ---: | ---: | ---: |
| Primeiro erro visível (baseline ingênua) | 0.000 | 0.522 | 0.376 |
| Passos mais próximos da resposta (baseline ingênua) | 0.000 | 0.652 | 0.300 |
| Heurística estrutural | 1.000 | 1.000 | 1.000 |
| Heurística com confirmação contrafactual | 1.000 | 1.000 | 1.000 |

O detalhamento completo, incluindo taxa de acerto por tipo de falha, está em `benchmarks/results/summary.md`.

Esses números pedem uma leitura honesta. A heurística estrutural atinge 1.000 nessa suíte principalmente porque cada falha injetada deixa uma assinatura que a biblioteca de sinais foi escrita para detectar. Isso prova que o pipeline funciona de ponta a ponta, mas não garante generalização para falhas inéditas, que é justamente o próximo passo a testar. Da mesma forma, o replay contrafactual confirmou o primeiro candidato em todas as falhas e não alterou o ranking aqui; o papel dele é descartar hipóteses erradas quando a heurística falhar.

Os números de triagem importam tanto quanto os de localização. Das 115 falhas, 90 foram escaladas para atendimento humano e 25 geraram uma resposta errada com alta confiança (todas vindas de documentos desatualizados ou drift de prompt). O gate existe justamente para barrar esse segundo grupo: qualquer mudança que transforme escalonamentos seguros em respostas erradas confiantes é uma regressão grave, mesmo quando a taxa geral de acerto parece boa.

### Como o diagnóstico funciona

O método completo está descrito em [docs/methodology.md](docs/methodology.md). De forma resumida, partindo do passo em que a resposta deu errado, o algoritmo percorre as arestas de dependência de trás para frente. Em cada etapa anterior, roda um conjunto de detectores: documento desatualizado, erro escondido dentro de um status de sucesso, identificador que não aparece nem na pergunta do usuário nem nos documentos recuperados, ou veredito dado sem chamar o cálculo de prazo. Cada sinal soma peso àquela etapa. Os candidatos são ordenados pelo peso total, desempatando em favor do passo mais antigo, já que uma causa anterior explica mais comportamentos seguintes.

Depois entra a etapa que transforma hipótese em evidência. Para cada um dos três primeiros candidatos, o sistema reexecuta a mesma entrada aplicando uma correção válida apenas naquele passo, usando dados da fonte oficial. Se a nova execução acertar a resposta, o candidato é confirmado; caso contrário, é descartado.

### Conexão com Langfuse e LangSmith

O agente não se comunica diretamente com nenhuma das duas plataformas. Ele exporta traces no padrão OTLP para um OpenTelemetry Collector, que replica a telemetria para ambas.

```bash
cp deploy/.env.example deploy/.env      # preencha suas chaves
set -a; source deploy/.env; set +a
docker run --rm -p 4318:4318 \
  --env-file deploy/.env \
  -v "$(pwd)/deploy/otel-collector.yaml:/etc/otelcol-contrib/config.yaml" \
  otel/opentelemetry-collector-contrib:latest

pip install -e ".[otlp]"
python -m support_agent "Can I still return PED-1004?"
```

Confirme os endpoints exatos e o formato dos headers na documentação do Langfuse e do LangSmith antes de usar em produção, pois ambos atualizam esses detalhes periodicamente.

### Estrutura do projeto

```text
src/
  support_agent/        agente, ferramentas, planner, injeção de falhas e cenários
    agent.py            loop de decisão com um span por decisão e por ferramenta
    planner.py          planner baseado em regras (simula a decisão do LLM)
    faults.py           falhas controladas aplicadas na fronteira do agente
    interventions.py    correções conhecidas usadas no replay contrafactual
    scenarios.py        suíte de 210 cenários e respostas esperadas
    evaluation.py       funções compartilhadas de execução, replay e gate
  causal_diagnosis/     lê apenas spans; sem dependência direta do agente
    graph.py            monta etapas e arestas de dependência a partir dos spans
    signals.py          detectores de anomalias e seus pesos
    localize.py         ranqueamento, baselines e ponto de entrada diagnose()
    counterfactual.py   confirmação de causa raiz via replay
    metrics.py          métricas Hit@k e MRR
tests/                  testes de comportamento do agente, localização e gate
benchmarks/             executor de benchmark e resultados salvos
scripts/                script do gate de regressão para CI
deploy/                 configuração do OpenTelemetry Collector e template de env
docs/                   arquitetura e metodologia
```

### Limitações

* **Falhas sintéticas:** As cinco falhas foram criadas manualmente e refletem cenários previstos, não a combinação imprevisível de erros que acontece em tráfego real.
* **Planner baseado em regras:** Manter o planner determinístico deixa as execuções rápidas e sem custo de API. Com um LLM real no planner, o replay contrafactual exige reproduzir as saídas gravadas do modelo até o passo corrigido em vez de rodar tudo do zero (detalhado na metodologia, ainda não implementado).
* **Dependência de um verificador:** A confirmação contrafactual precisa de algo que diga se a resposta corrigida está certa. No benchmark esse papel é feito pelo gabarito; em produção, exige uma checagem determinística nos dados originais ou expectativas rotuladas, caso contrário o sistema fica apenas com o ranking da heurística.
* **Sem juiz LLM por span ou painel visual:** A heurística estrutural serve como linha de base que um futuro juiz LLM precisará superar. Também não há dashboard web ainda, embora o benchmark já registre métricas operacionais como taxa de escalonamento, custo por tarefa e latência p95.

### Roadmap

* Substituir o planner por um modelo LLM com gravação de saídas para testar o replay contrafactual em execuções reais.
* Criar categorias de falhas inéditas que não tenham detectores feitos sob medida, medindo a capacidade real de generalização.
* Adicionar um juiz LLM em nível de span calibrado com anotações humanas via kappa de Cohen.

### Licença

MIT. Veja [LICENSE](LICENSE).
