import { cloudflareTest } from "@cloudflare/vitest-pool-workers";
import { defineConfig } from "vitest/config";

/**
 * Tests run inside workerd via @cloudflare/vitest-pool-workers, so Durable Object
 * SQLite storage, R2 and the worker are exercised for real.
 *
 * - `wrangler.test.jsonc` is a slim copy of the production config: no custom routes and
 *   no outbound send binding, so a test run can never deliver mail.
 * - `remoteBindings: false` keeps the pool fully local; without it the pool opens a
 *   remote proxy session and demands CLOUDFLARE_API_TOKEN even for local tests.
 *
 * On pool-workers <= 0.21 / vitest 3 the shape differs (`defineWorkersConfig` from
 * `@cloudflare/vitest-pool-workers/config`); see the package's vitest-v3-to-v4 codemod.
 */
export default defineConfig({
	plugins: [
		cloudflareTest({
			wrangler: { configPath: "./wrangler.test.jsonc" },
			remoteBindings: false,
		}),
	],
	test: {
		include: ["tests/**/*.test.ts"],
	},
});
