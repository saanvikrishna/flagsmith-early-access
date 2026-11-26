import express from 'express';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { createFlagsmithClient, FEATURE_FLAGS } from './flagsmithClient.js';
import { DEMO_USERS, findUserById, getUserTraits } from './users.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PUBLIC_DIR = path.resolve(__dirname, '..', 'public');

export function createApp(options = {}) {
  const app = express();
  const flagsmith = options.flagsmithClient ?? createFlagsmithClient(options.flagsmithOptions);

  app.use(express.json());
  app.use(express.static(PUBLIC_DIR));

  app.get('/health', (_req, res) => {
    res.json({
      status: 'ok',
      mode: flagsmith.getMode(),
      flags: FEATURE_FLAGS,
    });
  });

  app.get('/api/users', (_req, res) => {
    res.json({
      users: DEMO_USERS,
    });
  });

  app.get('/api/flags', async (req, res) => {
    const requestedUser = req.query.user ?? '1';
    const user = findUserById(requestedUser);

    if (!user) {
      return res.status(404).json({
        error: `Unknown user: ${requestedUser}`,
      });
    }

    try {
      const traits = getUserTraits(user);
      const flags = await flagsmith.getIdentityFlags(user.id, traits);
      return res.json({
        user,
        mode: flagsmith.getMode(),
        flags,
      });
    } catch (err) {
      return res.status(502).json({
        error: err.message || 'Failed to fetch flags from Flagsmith',
      });
    }
  });

  return app;
}

const isMain = process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href;
if (isMain) {
  const port = Number(process.env.PORT || 3000);
  const app = createApp();
  app.listen(port, () => {
    console.log(`Projects Dashboard listening on http://localhost:${port}`);
  });
}
