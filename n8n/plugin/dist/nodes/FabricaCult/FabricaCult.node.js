"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.FabricaCult = void 0;
/**
 * Nó declarativo: cada operação vira uma chamada HTTP ao worker.
 * Editar artifact -> devolve job_id; use "Esperar" com callback ou "Status" em loop.
 */
class FabricaCult {
    constructor() {
        this.description = {
            displayName: 'Fábrica Cult',
            name: 'fabricaCult',
            icon: 'file:fabrica.svg',
            group: ['transform'],
            version: 1,
            subtitle: '={{ $parameter["operacao"] }}',
            description: 'Edita artifacts de cenas em vídeo (16:9 e 9:16) e cuida da pauta do canal',
            defaults: { name: 'Fábrica Cult' },
            inputs: ['main'],
            outputs: ['main'],
            credentials: [{ name: 'fabricaCultApi', required: true }],
            requestDefaults: {
                baseURL: '={{ $credentials.url }}',
                headers: { 'Content-Type': 'application/json' },
                timeout: 900000,
            },
            properties: [
                {
                    displayName: 'Operação',
                    name: 'operacao',
                    type: 'options',
                    noDataExpression: true,
                    default: 'editar',
                    options: [
                        {
                            name: 'Editar Artifact',
                            value: 'editar',
                            description: 'Narração, efeitos, trilha, transições, legenda, longo 16:9 e shorts 9:16',
                            action: 'Editar um artifact',
                            routing: {
                                request: {
                                    method: 'POST',
                                    url: '/edicao',
                                    body: {
                                        nome: '={{ $parameter["nome"] }}',
                                        artifact_base64: '={{ $parameter["artifactBase64"] }}',
                                        callback_url: '={{ $parameter["callbackUrl"] || undefined }}',
                                        opcoes: '={{ { shorts: $parameter["shorts"], max_shorts: $parameter["maxShorts"], clima_trilha: $parameter["clima"], trilha: $parameter["trilha"], trilha_arquivo: $parameter["trilhaArquivo"] || null, legenda_queimada_longo: $parameter["legendaLongo"] } }}',
                                    },
                                },
                            },
                        },
                        {
                            name: 'Status Do Job',
                            value: 'status',
                            action: 'Ver o andamento de uma edição',
                            routing: { request: { method: 'GET', url: '=/jobs/{{ $parameter["jobId"] }}' } },
                        },
                        {
                            name: 'Resultado Do Job',
                            value: 'resultado',
                            action: 'Listar os vídeos prontos de uma edição',
                            routing: { request: { method: 'GET', url: '=/jobs/{{ $parameter["jobId"] }}/resultado' } },
                        },
                        {
                            name: 'Baixar Arquivo',
                            value: 'arquivo',
                            action: 'Baixar um vídeo ou legenda pronta',
                            routing: {
                                request: {
                                    method: 'GET',
                                    url: '=/arquivos/{{ $parameter["jobId"] }}/{{ $parameter["arquivo"] }}',
                                    encoding: 'arraybuffer',
                                    json: false,
                                },
                                output: { postReceive: [{ type: 'binaryData', properties: { destinationProperty: 'data' } }] },
                            },
                        },
                        {
                            name: 'Ver Recursos Ativos',
                            value: 'saude',
                            description: 'Mostra quais vozes, sons, mapas e efeitos estão ligados no worker',
                            action: 'Ver os recursos ativos do worker',
                            routing: { request: { method: 'GET', url: '/saude' } },
                        },
                        {
                            name: 'Coletar Tendências',
                            value: 'tendencias',
                            action: 'Coletar o que está em alta no Brasil e fora',
                            routing: { request: { method: 'POST', url: '/pauta/tendencias' } },
                        },
                        {
                            name: 'Sugerir Pautas',
                            value: 'candidatos',
                            action: 'Sugerir 3 pautas a partir das tendências',
                            routing: { request: { method: 'POST', url: '/pauta/candidatos', body: { itens: '={{ $json.itens }}' } } },
                        },
                        {
                            name: 'Escrever Roteiro',
                            value: 'roteiro',
                            action: 'Escrever o roteiro em texto para a conversa de artifacts',
                            routing: { request: { method: 'POST', url: '/pauta/roteiro', body: { tema: '={{ $parameter["tema"] }}' } } },
                        },
                    ],
                },
                { displayName: 'Nome Do Vídeo', name: 'nome', type: 'string', default: '={{ $json.name }}', displayOptions: { show: { operacao: ['editar'] } } },
                { displayName: 'Artifact (Base64)', name: 'artifactBase64', type: 'string', default: '', required: true, description: 'Conteúdo do .html do artifact em base64', displayOptions: { show: { operacao: ['editar'] } } },
                { displayName: 'URL De Retorno', name: 'callbackUrl', type: 'string', default: '={{ $execution.resumeUrl }}', description: 'Webhook chamado quando a edição terminar (use com o nó Wait)', displayOptions: { show: { operacao: ['editar'] } } },
                { displayName: 'Gerar Shorts', name: 'shorts', type: 'boolean', default: true, displayOptions: { show: { operacao: ['editar'] } } },
                { displayName: 'Máximo De Shorts', name: 'maxShorts', type: 'number', default: 3, displayOptions: { show: { operacao: ['editar'] } } },
                { displayName: 'Trilha', name: 'trilha', type: 'boolean', default: true, displayOptions: { show: { operacao: ['editar'] } } },
                {
                    displayName: 'Clima Da Trilha', name: 'clima', type: 'options', default: 'reflexivo',
                    options: [{ name: 'Reflexivo', value: 'reflexivo' }, { name: 'Mistério', value: 'misterio' }, { name: 'Tensão', value: 'tensao' }],
                    displayOptions: { show: { operacao: ['editar'] } },
                },
                { displayName: 'Trilha Própria (URL ou Caminho)', name: 'trilhaArquivo', type: 'string', default: '', description: 'Vazio = biblioteca, ACE-Step ou Openverse', displayOptions: { show: { operacao: ['editar'] } } },
                { displayName: 'Legenda Queimada No Longo', name: 'legendaLongo', type: 'boolean', default: false, displayOptions: { show: { operacao: ['editar'] } } },
                { displayName: 'Job ID', name: 'jobId', type: 'string', default: '={{ $json.job_id }}', displayOptions: { show: { operacao: ['status', 'resultado', 'arquivo'] } } },
                { displayName: 'Arquivo', name: 'arquivo', type: 'string', default: '={{ $json.nome }}', displayOptions: { show: { operacao: ['arquivo'] } } },
                { displayName: 'Tema', name: 'tema', type: 'json', default: '={{ $json.tema }}', displayOptions: { show: { operacao: ['roteiro'] } } },
            ],
        };
    }
}
exports.FabricaCult = FabricaCult;
