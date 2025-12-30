import { appendFileSync, mkdirSync } from 'fs';
import path from 'path';

const LOG_DIR = path.resolve('logs');
const LOG_FILE = path.join(LOG_DIR, 'server.log');

// Ensure log directory exists
try {
	mkdirSync(LOG_DIR, { recursive: true });
} catch {}

export function log(context: string, message: string, data?: unknown) {
	const timestamp = new Date().toISOString();
	let line = `[${timestamp}] [${context}] ${message}`;
	if (data !== undefined) {
		line += ` ${typeof data === 'object' ? JSON.stringify(data) : data}`;
	}
	line += '\n';

	appendFileSync(LOG_FILE, line);
}

export function clearLog() {
	const { writeFileSync } = require('fs');
	writeFileSync(LOG_FILE, '');
}
