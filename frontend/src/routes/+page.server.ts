import { fail, redirect } from '@sveltejs/kit';
import { writeFile, mkdir } from 'fs/promises';
import { existsSync } from 'fs';
import { spawn } from 'child_process';
import path from 'path';
import type { Actions } from './$types';
import { log } from '$lib/server/logger';

const UPLOADS_DIR = path.resolve('uploads');
const PARSER_PATH = path.resolve('../hoi4_parser/target/release/hoi4_parser.exe');

async function runParser(savePath: string, outputPath: string): Promise<boolean> {
	return new Promise((resolve) => {
		log('Parser', 'Starting', { savePath, outputPath });

		const parser = spawn(PARSER_PATH, [savePath, outputPath], {
			cwd: path.dirname(PARSER_PATH)
		});

		parser.stdout.on('data', (data) => log('Parser', 'stdout', data.toString().trim()));
		parser.stderr.on('data', (data) => log('Parser', 'stderr', data.toString().trim()));
		parser.on('close', (code) => {
			log('Parser', 'Exited', { code });
			resolve(code === 0);
		});
		parser.on('error', (err) => {
			log('Parser', 'Error', err.message);
			resolve(false);
		});
	});
}

export const actions: Actions = {
	upload: async ({ request }) => {
		log('Upload', 'Started');
		const formData = await request.formData();
		const file = formData.get('savefile') as File | null;

		if (!file || file.size === 0) {
			log('Upload', 'No file provided');
			return fail(400, { message: 'No file provided' });
		}

		log('Upload', 'File received', { name: file.name, size: file.size });

		if (!file.name.endsWith('.hoi4')) {
			return fail(400, { message: 'Invalid file type. Please upload a .hoi4 save file' });
		}

		if (!existsSync(PARSER_PATH)) {
			log('Upload', 'Parser not found', PARSER_PATH);
			return fail(500, { message: 'Parser not found. Please build the Rust parser first.' });
		}

		if (!existsSync(UPLOADS_DIR)) {
			await mkdir(UPLOADS_DIR, { recursive: true });
		}

		const saveId = Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
		const saveDir = path.join(UPLOADS_DIR, saveId);

		try {
			await mkdir(saveDir, { recursive: true });

			const savePath = path.join(saveDir, 'save.hoi4');
			log('Upload', 'Writing file');
			const buffer = Buffer.from(await file.arrayBuffer());
			await writeFile(savePath, buffer);
			log('Upload', 'File written', { bytes: buffer.length });

			const outputPath = path.join(saveDir, 'data.json');
			log('Upload', 'Running parser');
			const success = await runParser(savePath, outputPath);

			if (!success) {
				log('Upload', 'Parser failed');
				return fail(500, { message: 'Failed to parse save file' });
			}

			if (!existsSync(outputPath)) {
				log('Upload', 'No output file');
				return fail(500, { message: 'Parser did not produce output' });
			}

			log('Upload', 'Success', { saveId });
		} catch (error) {
			log('Upload', 'Error', (error as Error).message);
			return fail(500, { message: 'Failed to process save file' });
		}

		redirect(303, `/saves/${saveId}`);
	}
};
