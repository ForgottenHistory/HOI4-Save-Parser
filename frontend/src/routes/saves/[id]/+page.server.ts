import { error } from '@sveltejs/kit';
import { readFile } from 'fs/promises';
import { existsSync } from 'fs';
import path from 'path';
import type { PageServerLoad } from './$types';

const UPLOADS_DIR = path.resolve('uploads');

export interface GameData {
	metadata: {
		player: string;
		date: string;
		total_countries: number;
		active_countries: number;
	};
	events: string[];
	countries: Array<{
		tag: string;
		data: {
			stability: number;
			war_support: number;
			politics: {
				ruling_party: string;
				political_power: number;
				parties: Record<string, {
					popularity: number;
					country_leader?: Array<{
						character: {
							id: number;
							name: string;
							type: number;
						};
						ideology: string;
					}>;
				}>;
				ideas: string[];
				elections_allowed: boolean;
				last_election: string;
			};
			focus?: {
				current?: string;
				progress?: number;
				completed?: string[];
				paused?: string;
			};
			major?: boolean | null;
			variables?: Record<string, number>;
		};
	}>;
}

export const load: PageServerLoad = async ({ params }) => {
	const saveDir = path.join(UPLOADS_DIR, params.id);
	const dataPath = path.join(saveDir, 'data.json');

	if (!existsSync(dataPath)) {
		throw error(404, 'Save not found');
	}

	try {
		const content = await readFile(dataPath, 'utf-8');
		const gameData: GameData = JSON.parse(content);

		// Find player country
		const playerCountry = gameData.countries.find(c => c.tag === gameData.metadata.player);

		return {
			saveId: params.id,
			metadata: gameData.metadata,
			playerCountry
		};
	} catch (e) {
		console.error('Failed to load save data:', e);
		throw error(500, 'Failed to load save data');
	}
};
