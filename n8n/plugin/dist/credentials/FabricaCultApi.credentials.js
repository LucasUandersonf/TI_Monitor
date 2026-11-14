"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.FabricaCultApi = void 0;
class FabricaCultApi {
    constructor() {
        this.name = 'fabricaCultApi';
        this.displayName = 'Fábrica Cult (worker)';
        this.properties = [
            { displayName: 'URL do worker', name: 'url', type: 'string', default: 'http://worker:8000' },
        ];
    }
}
exports.FabricaCultApi = FabricaCultApi;
