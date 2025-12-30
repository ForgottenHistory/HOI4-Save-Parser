<script lang="ts">
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();

	function formatDate(dateStr: string): string {
		// HOI4 date format: "1936.3.1.2" -> "1 March 1936"
		const months = ['January', 'February', 'March', 'April', 'May', 'June',
			'July', 'August', 'September', 'October', 'November', 'December'];
		const parts = dateStr.split('.');
		if (parts.length >= 3) {
			const year = parts[0];
			const month = parseInt(parts[1]) - 1;
			const day = parts[2];
			return `${day} ${months[month]} ${year}`;
		}
		return dateStr;
	}

	function getLeaderName(country: typeof data.playerCountry): string {
		if (!country) return 'Unknown';
		const rulingParty = country.data.politics.ruling_party;
		const party = country.data.politics.parties[rulingParty];
		if (party?.country_leader?.[0]) {
			const name = party.country_leader[0].character.name;
			// Clean up localization keys like "GER_adolf_hitler" -> "Adolf Hitler"
			if (name.includes('_')) {
				return name.split('_').slice(1).map(w =>
					w.charAt(0).toUpperCase() + w.slice(1)
				).join(' ');
			}
			return name;
		}
		return 'Unknown';
	}

	function formatIdeology(ideology: string): string {
		return ideology.charAt(0).toUpperCase() + ideology.slice(1);
	}

	function formatPercentage(value: number): string {
		return Math.round(value * 100) + '%';
	}
</script>

<div class="min-h-screen bg-gray-900 text-gray-100">
	<div class="container mx-auto px-4 py-8 max-w-4xl">
		<a href="/" class="text-blue-400 hover:text-blue-300 mb-6 inline-block">&larr; Upload another save</a>

		<header class="mb-8">
			<h1 class="text-3xl font-bold mb-2">Save Analysis</h1>
			<p class="text-gray-400">{formatDate(data.metadata.date)}</p>
		</header>

		{#if data.playerCountry}
			{@const country = data.playerCountry}
			{@const politics = country.data.politics}

			<div class="bg-gray-800 rounded-lg p-6 mb-6">
				<div class="flex items-center gap-4 mb-6">
					<div class="w-16 h-16 bg-gray-700 rounded-lg flex items-center justify-center text-2xl font-bold">
						{country.tag}
					</div>
					<div>
						<h2 class="text-2xl font-bold">{country.tag}</h2>
						<p class="text-gray-400">Led by {getLeaderName(country)}</p>
					</div>
				</div>

				<div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
					<div class="bg-gray-700 rounded-lg p-4">
						<p class="text-gray-400 text-sm">Ruling Party</p>
						<p class="text-lg font-semibold">{formatIdeology(politics.ruling_party)}</p>
					</div>
					<div class="bg-gray-700 rounded-lg p-4">
						<p class="text-gray-400 text-sm">Political Power</p>
						<p class="text-lg font-semibold">{Math.round(politics.political_power)}</p>
					</div>
					<div class="bg-gray-700 rounded-lg p-4">
						<p class="text-gray-400 text-sm">Stability</p>
						<p class="text-lg font-semibold">{formatPercentage(country.data.stability)}</p>
					</div>
					<div class="bg-gray-700 rounded-lg p-4">
						<p class="text-gray-400 text-sm">War Support</p>
						<p class="text-lg font-semibold">{formatPercentage(country.data.war_support)}</p>
					</div>
				</div>

				<div class="mb-6">
					<h3 class="text-lg font-semibold mb-3">Party Popularity</h3>
					<div class="space-y-2">
						{#each Object.entries(politics.parties).filter(([_, p]) => p != null) as [ideology, party]}
							{@const colors: Record<string, string> = {
								fascism: 'bg-amber-700',
								democratic: 'bg-blue-600',
								communism: 'bg-red-700',
								neutrality: 'bg-gray-600'
							}}
							<div>
								<div class="flex justify-between text-sm mb-1">
									<span>{formatIdeology(ideology)}</span>
									<span>{party.popularity ?? 0}%</span>
								</div>
								<div class="h-2 bg-gray-700 rounded-full overflow-hidden">
									<div
										class="{colors[ideology] || 'bg-gray-500'} h-full rounded-full transition-all"
										style="width: {party.popularity ?? 0}%"
									></div>
								</div>
							</div>
						{/each}
					</div>
				</div>

				{#if country.data.focus}
					<div class="mb-6">
						<h3 class="text-lg font-semibold mb-3">National Focus</h3>
						{#if country.data.focus.current}
							<div class="bg-gray-700 rounded-lg p-4">
								<p class="text-gray-400 text-sm">Currently Researching</p>
								<p class="font-medium">{country.data.focus.current.replace(/_/g, ' ')}</p>
								{#if country.data.focus.progress}
									<div class="mt-2">
										<div class="h-2 bg-gray-600 rounded-full overflow-hidden">
											<div
												class="bg-green-500 h-full rounded-full"
												style="width: {(country.data.focus.progress / 70) * 100}%"
											></div>
										</div>
										<p class="text-sm text-gray-400 mt-1">{Math.round(country.data.focus.progress)} / 70 days</p>
									</div>
								{/if}
							</div>
						{:else}
							<p class="text-gray-400">No focus in progress</p>
						{/if}

						{#if country.data.focus.completed && country.data.focus.completed.length > 0}
							<div class="mt-4">
								<p class="text-gray-400 text-sm mb-2">Completed Focuses ({country.data.focus.completed.length})</p>
								<div class="flex flex-wrap gap-2">
									{#each country.data.focus.completed.slice(0, 10) as focus}
										<span class="px-2 py-1 bg-gray-700 rounded text-sm">{focus.replace(/_/g, ' ')}</span>
									{/each}
									{#if country.data.focus.completed.length > 10}
										<span class="px-2 py-1 bg-gray-600 rounded text-sm">+{country.data.focus.completed.length - 10} more</span>
									{/if}
								</div>
							</div>
						{/if}
					</div>
				{/if}

				{#if politics.ideas && politics.ideas.length > 0}
					<div>
						<h3 class="text-lg font-semibold mb-3">National Ideas</h3>
						<div class="flex flex-wrap gap-2">
							{#each politics.ideas as idea}
								<span class="px-2 py-1 bg-gray-700 rounded text-sm">{idea.replace(/_/g, ' ')}</span>
							{/each}
						</div>
					</div>
				{/if}
			</div>

			<div class="bg-gray-800 rounded-lg p-6">
				<h3 class="text-lg font-semibold mb-3">Game Info</h3>
				<div class="grid grid-cols-2 gap-4 text-sm">
					<div>
						<p class="text-gray-400">Active Countries</p>
						<p>{data.metadata.active_countries}</p>
					</div>
					<div>
						<p class="text-gray-400">Total Countries</p>
						<p>{data.metadata.total_countries}</p>
					</div>
				</div>
			</div>
		{:else}
			<div class="bg-red-900/50 text-red-300 rounded-lg p-6">
				<p>Could not find player country data for {data.metadata.player}</p>
			</div>
		{/if}
	</div>
</div>
