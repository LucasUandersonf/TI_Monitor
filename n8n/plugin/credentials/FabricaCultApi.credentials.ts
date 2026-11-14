import type { ICredentialType, INodeProperties } from 'n8n-workflow';

export class FabricaCultApi implements ICredentialType {
	name = 'fabricaCultApi';
	displayName = 'Fábrica Cult (worker)';
	properties: INodeProperties[] = [
		{ displayName: 'URL do worker', name: 'url', type: 'string', default: 'http://worker:8000' },
	];
}
