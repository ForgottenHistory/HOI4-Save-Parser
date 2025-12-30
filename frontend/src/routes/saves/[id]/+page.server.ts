import { error } from '@sveltejs/kit';
import { readFile } from 'fs/promises';
import { existsSync } from 'fs';
import path from 'path';
import type { PageServerLoad } from './$types';
import { getCountryName, getPartyName, localize } from '$lib/server/localization';

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
					popularity?: number;
					name?: string;
					long_name?: string;
					country_leader?: Array<{
						character: {
							id: number;
							name: string;
							type: number;
						};
						ideology: string;
					}>;
				} | null>;
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

		// Get localized country name and ruling party
		const rulingParty = playerCountry?.data.politics?.ruling_party;
		const countryName = getCountryName(gameData.metadata.player, rulingParty ?? undefined);

		// Get party name from save data first, then fallback to localization
		const rulingPartyData = rulingParty && playerCountry?.data.politics?.parties
			? playerCountry.data.politics.parties[rulingParty]
			: null;
		const partyNameFromSave = rulingPartyData?.long_name ?? rulingPartyData?.name;

		const partyInfo = rulingParty
			? getPartyName(gameData.metadata.player, rulingParty, partyNameFromSave ?? undefined)
			: { party: 'Unknown', ideologyName: 'Unknown' };

		// Localize ideas
		const localizedIdeas = playerCountry?.data.politics?.ideas?.map(idea => ({
			key: idea,
			name: localize(idea)
		})) ?? [];

		// Localize focuses
		const currentFocus = playerCountry?.data.focus?.current;
		const localizedCurrentFocus = currentFocus ? {
			key: currentFocus,
			name: localize(currentFocus)
		} : null;

		const localizedCompletedFocuses = playerCountry?.data.focus?.completed?.map(focus => ({
			key: focus,
			name: localize(focus)
		})) ?? [];

		return {
			saveId: params.id,
			metadata: gameData.metadata,
			playerCountry,
			countryName,
			partyInfo,
			localizedIdeas,
			localizedCurrentFocus,
			localizedCompletedFocuses
		};
	} catch (e) {
		console.error('Failed to load save data:', e);
		throw error(500, 'Failed to load save data');
	}
};
