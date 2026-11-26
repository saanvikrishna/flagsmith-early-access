export const DEMO_USERS = [
  {
    id: '1',
    identifier: 'user_1',
    name: 'Alice',
    role: 'VP Engineering',
    org_id: 'acme',
    orgName: 'Acme Corp',
    plan: 'enterprise',
  },
  {
    id: '2',
    identifier: 'user_2',
    name: 'Bob',
    role: 'Staff Engineer',
    org_id: 'acme',
    orgName: 'Acme Corp',
    plan: 'enterprise',
  },
  {
    id: '3',
    identifier: 'user_3',
    name: 'Carol',
    role: 'Product Manager',
    org_id: 'globex',
    orgName: 'Globex Inc',
    plan: 'pro',
  },
  {
    id: '4',
    identifier: 'user_4',
    name: 'Dave',
    role: 'Data Analyst',
    org_id: 'globex',
    orgName: 'Globex Inc',
    plan: 'pro',
  },
  {
    id: '5',
    identifier: 'user_5',
    name: 'Eve',
    role: 'Operations Lead',
    org_id: 'initech',
    orgName: 'Initech',
    plan: 'starter',
  },
  {
    id: '42',
    identifier: 'user_42',
    name: 'Frank',
    role: 'Developer',
    org_id: 'initech',
    orgName: 'Initech',
    plan: 'starter',
  },
];

export function findUserById(userId) {
  const normalized = String(userId ?? '').replace(/^user_/, '');
  return DEMO_USERS.find((u) => u.id === normalized) ?? null;
}

export function buildIdentifier(userId) {
  const raw = String(userId ?? '').trim();
  return raw.startsWith('user_') ? raw : `user_${raw}`;
}

export function getUserTraits(user) {
  return {
    org_id: user.org_id,
    plan: user.plan,
  };
}
