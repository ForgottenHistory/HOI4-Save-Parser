import { fail } from '@sveltejs/kit';
import { writeFile, mkdir } from 'fs/promises';
import { existsSync } from 'fs';
import path from 'path';
import type { Actions } from './$types';

const UPLOADS_DIR = path.resolve('uploads');

export const actions: Actions = {
	upload: async ({ request }) => {
		const formData = await request.formData();
		const file = formData.get('savefile') as File | null;

		if (!file || file.size === 0) {
			return fail(400, { message: 'No file provided' });
		}

		if (!file.name.endsWith('.hoi4')) {
			return fail(400, { message: 'Invalid file type. Please upload a .hoi4 save file' });
		}

		try {
			// Ensure uploads directory exists
			if (!existsSync(UPLOADS_DIR)) {
				await mkdir(UPLOADS_DIR, { recursive: true });
			}

			// Generate unique filename with timestamp
			const timestamp = Date.now();
			const safeName = file.name.replace(/[^a-zA-Z0-9._-]/g, '_');
			const filename = `${timestamp}_${safeName}`;
			const filepath = path.join(UPLOADS_DIR, filename);

			// Write file to disk
			const buffer = Buffer.from(await file.arrayBuffer());
			await writeFile(filepath, buffer);

			return {
				success: true,
				filename,
				message: `Successfully uploaded ${file.name}`
			};
		} catch (error) {
			console.error('Upload error:', error);
			return fail(500, { message: 'Failed to save file' });
		}
	}
};
