import { readFileSync, readdirSync } from 'fs';
import path from 'path';
import { env } from '$env/dynamic/private';

const HOI4_DIR = env.HOI4_GAME_DIR ?? 'C:/Program Files (x86)/Steam/steamapps/common/Hearts of Iron IV';
const LOCALE_DIR = path.join(HOI4_DIR, 'localisation', 'english');

let localeCache: Map<string, string> | null = null;

function parseLocaleFile(content: string): Map<string, string> {
	const map = new Map<string, string>();
	const lines = content.split('\n');

	for (const line of lines) {
		// Match pattern: KEY:0 "Value" or KEY: "Value" (version number optional, allow hyphens in key)
		const match = line.match(/^\s*([A-Za-z0-9_-]+):\d*\s*"([^"]*)"/);
		if (match) {
			map.set(match[1], match[2]);
		}
	}

	return map;
}

function loadAllLocales(): Map<string, string> {
	const combined = new Map<string, string>();

	try {
		const files = readdirSync(LOCALE_DIR).filter(f => f.endsWith('.yml'));

		for (const file of files) {
			const content = readFileSync(path.join(LOCALE_DIR, file), 'utf-8');
			const parsed = parseLocaleFile(content);
			for (const [key, value] of parsed) {
				combined.set(key, value);
			}
		}
	} catch (e) {
		console.error('Failed to load localization files:', e);
	}

	return combined;
}

function getLocales(): Map<string, string> {
	if (!localeCache) {
		localeCache = loadAllLocales();
	}
	return localeCache;
}

function cleanKeyForDisplay(key: string): string {
	let cleaned = key;
	// Remove country prefix (e.g., "NOR_" from "NOR_some_idea")
	cleaned = cleaned.replace(/^[A-Z]{3}_/, '');
	// Remove common suffixes
	cleaned = cleaned.replace(/_ns$/, '');
	cleaned = cleaned.replace(/_idea$/, '');
	cleaned = cleaned.replace(/_focus$/, '');
	// Replace underscores with spaces and title case
	cleaned = cleaned.replace(/_/g, ' ');
	cleaned = cleaned.replace(/\b\w/g, c => c.toUpperCase());
	return cleaned;
}

export function localize(key: string): string {
	const locales = getLocales();

	if (locales.has(key)) {
		return locales.get(key)!;
	}

	// Try lowercase/uppercase variations
	if (locales.has(key.toLowerCase())) {
		return locales.get(key.toLowerCase())!;
	}

	// Fallback to cleaned display name
	return cleanKeyForDisplay(key);
}

export function getCountryName(tag: string, ideology?: string): string {
	const locales = getLocales();

	// Try ideology-specific name first (e.g., GER_fascism)
	if (ideology) {
		const ideologyKey = `${tag}_${ideology}`;
		if (locales.has(ideologyKey)) {
			return locales.get(ideologyKey)!;
		}
	}

	// Fall back to base country name (e.g., GER)
	return locales.get(tag) ?? tag;
}

export function getPartyName(tag: string, ideology: string, partyKeyFromSave?: string): { party: string; ideologyName: string } {
	const locales = getLocales();

	let party: string | null = null;

	// If save has a custom party name key, try to localize it
	if (partyKeyFromSave) {
		// Try the key directly, then with _long and _long_name variants
		party = locales.get(partyKeyFromSave)
			?? locales.get(`${partyKeyFromSave}_long`)
			?? locales.get(`${partyKeyFromSave}_long_name`)
			?? null;
	}

	// Fallback to standard party name pattern (e.g., NOR_neutrality_party)
	if (!party) {
		const partyKey = `${tag}_${ideology}_party_long`;
		const partyKeyShort = `${tag}_${ideology}_party`;
		party = locales.get(partyKey) ?? locales.get(partyKeyShort) ?? null;
	}

	// Get ideology display name (e.g., "Non-Aligned")
	const ideologyName = locales.get(ideology) ?? cleanKeyForDisplay(ideology);

	return {
		party: party ?? ideologyName,
		ideologyName
	};
}

export function getLocalizedData() {
	const locales = getLocales();
	// Return a plain object for serialization
	return Object.fromEntries(locales);
}
