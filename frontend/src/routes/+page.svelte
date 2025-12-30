<script lang="ts">
	import { enhance } from '$app/forms';

	let isDragging = $state(false);
	let selectedFile = $state<File | null>(null);
	let isUploading = $state(false);
	let uploadResult = $state<{ success: boolean; message: string } | null>(null);
	let fileInput = $state<HTMLInputElement | null>(null);

	// Sync selectedFile to the form's file input when both are available
	$effect(() => {
		if (fileInput && selectedFile) {
			const dt = new DataTransfer();
			dt.items.add(selectedFile);
			fileInput.files = dt.files;
		}
	});

	function handleDragOver(e: DragEvent) {
		e.preventDefault();
		isDragging = true;
	}

	function handleDragLeave(e: DragEvent) {
		e.preventDefault();
		isDragging = false;
	}

	function handleDrop(e: DragEvent) {
		e.preventDefault();
		isDragging = false;

		const file = e.dataTransfer?.files[0];
		if (file && file.name.endsWith('.hoi4')) {
			selectedFile = file;
			uploadResult = null;
		} else {
			uploadResult = { success: false, message: 'Please select a valid .hoi4 save file' };
		}
	}

	function handleFileSelect(e: Event) {
		const input = e.target as HTMLInputElement;
		const file = input.files?.[0];
		if (file) {
			selectedFile = file;
			uploadResult = null;
		}
	}

	function formatFileSize(bytes: number): string {
		if (bytes < 1024) return bytes + ' B';
		if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
		return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
	}
</script>

<div class="min-h-screen bg-gray-900 text-gray-100">
	<div class="container mx-auto px-4 py-12 max-w-2xl">
		<header class="text-center mb-12">
			<h1 class="text-4xl font-bold mb-2">HOI4 Save Analyzer</h1>
			<p class="text-gray-400">Upload your Hearts of Iron 4 save file to extract and view game data</p>
		</header>

		<div
			class="border-2 border-dashed rounded-lg p-12 text-center transition-colors {isDragging
				? 'border-blue-500 bg-blue-500/10'
				: 'border-gray-600 hover:border-gray-500'}"
			ondragover={handleDragOver}
			ondragleave={handleDragLeave}
			ondrop={handleDrop}
			role="button"
			tabindex="0"
		>
			<div class="mb-4">
				<svg class="w-16 h-16 mx-auto text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
					<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
				</svg>
			</div>

			<p class="text-lg mb-2">Drag and drop your save file here</p>
			<p class="text-gray-500 mb-4">or</p>

			<label class="inline-block cursor-pointer">
				<span class="px-6 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg font-medium transition-colors">
					Browse Files
				</span>
				<input
					type="file"
					accept=".hoi4"
					class="hidden"
					onchange={handleFileSelect}
				/>
			</label>

			<p class="text-gray-500 text-sm mt-4">Supports .hoi4 save files</p>
		</div>

		{#if selectedFile}
			<form
				method="POST"
				action="?/upload"
				enctype="multipart/form-data"
				use:enhance={() => {
					isUploading = true;
					uploadResult = null;
					return async ({ result }) => {
						isUploading = false;
						if (result.type === 'redirect') {
							window.location.href = result.location;
						} else if (result.type === 'failure') {
							uploadResult = { success: false, message: result.data?.message || 'Upload failed' };
						}
					};
				}}
				class="mt-6 p-4 bg-gray-800 rounded-lg"
			>
				<div class="flex items-center justify-between">
					<div class="flex items-center gap-3">
						<svg class="w-8 h-8 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
						</svg>
						<div>
							<p class="font-medium">{selectedFile.name}</p>
							<p class="text-sm text-gray-400">{formatFileSize(selectedFile.size)}</p>
						</div>
					</div>
					<button
						type="submit"
						disabled={isUploading}
						class="px-6 py-2 bg-green-600 hover:bg-green-700 disabled:bg-gray-600 disabled:cursor-not-allowed rounded-lg font-medium transition-colors"
					>
						{isUploading ? 'Processing...' : 'Analyze'}
					</button>
				</div>
				<input
					bind:this={fileInput}
					type="file"
					name="savefile"
					accept=".hoi4"
					class="hidden"
				/>
			</form>
		{/if}

		{#if uploadResult}
			<div class="mt-4 p-4 rounded-lg {uploadResult.success ? 'bg-green-900/50 text-green-300' : 'bg-red-900/50 text-red-300'}">
				{uploadResult.message}
			</div>
		{/if}
	</div>
</div>
