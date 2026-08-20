<script lang="ts">
	import '../app.css';
	import { page } from '$app/state';
	import { resolve } from '$app/paths';
	import favicon from '$lib/assets/favicon.svg';

	let { children } = $props();

	const tabs: { href: '/' | '/library'; label: string }[] = [
		{ href: '/', label: 'Dashboard' },
		{ href: '/library', label: 'Library' }
	];
</script>

<svelte:head>
	<link rel="icon" href={favicon} />
</svelte:head>

<div class="bg-background text-foreground min-h-screen">
	<nav class="border-border border-b">
		<div class="mx-auto flex max-w-3xl gap-1 px-4 sm:px-6 md:px-8">
			{#each tabs as tab (tab.href)}
				<a
					href={resolve(tab.href)}
					class="border-b-2 px-3 py-3 text-sm font-medium transition-colors {page.url.pathname ===
					tab.href
						? 'text-foreground border-sky-400'
						: 'text-muted-foreground hover:text-foreground border-transparent'}"
				>
					{tab.label}
				</a>
			{/each}
		</div>
	</nav>
	{@render children()}
</div>
