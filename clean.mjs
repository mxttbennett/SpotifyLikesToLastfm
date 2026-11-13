// Reads [{artist, title}] on stdin, prints the titles scrubbler would leave in Last.fm.
import { readFileSync } from 'node:fs';

const ROOT = '/opt/scrubbler';
process.loadEnvFile(`${ROOT}/.env`);
const { loadConfig } = await import(`${ROOT}/dist/core/config.js`);
const { createDb } = await import(`${ROOT}/dist/db/index.js`);
const { TierStore } = await import(`${ROOT}/dist/rules/tierStore.js`);
const { CustomRules } = await import(`${ROOT}/dist/rules/customRules.js`);
const { cleanTitle } = await import(`${ROOT}/dist/rules/engine.js`);

const config = loadConfig();
const db = createDb(config.dbPath.startsWith('/') ? config.dbPath : `${ROOT}/${config.dbPath}`);
const tiers = new TierStore(db, config.tiers, {
  approvalMode: config.approvalMode,
  discordConfigured: true,
  explicitTiers: config.explicitTiers,
});
const lookup = new CustomRules(db).lookup;

const tracks = JSON.parse(readFileSync(0, 'utf8'));
const out = tracks.map(({ artist, title }) =>
  cleanTitle(title, 'track', tiers.enabled(), { artist, lookup })?.clean ?? title,
);
process.stdout.write(JSON.stringify(out));
