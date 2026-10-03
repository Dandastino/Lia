// Fully mocked backend for the E2E tests: nothing here ever reaches a real API.

export const ADMIN = { id: 'u-admin', email: 'admin@lia.test', role: 'owner', org_id: 'o1' };
export const REGULAR = { id: 'u-user', email: 'user@lia.test', role: 'user', org_id: 'o1' };

const json = (route, status, body) =>
  route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });

/**
 * Registers mocks for every endpoint the app uses and returns the mutable
 * state plus a log of the requests the UI sent (to assert on payloads).
 */
export async function mockApi(page, { sessionExpired = false } = {}) {
  const state = {
    organizations: [{ id: 'o1', name: 'Acme', industry: 'Tech', connector_type: 'internal', user_count: 1 }],
    users: [{ id: 'u-admin', email: ADMIN.email, role: 'owner', org_id: 'o1', org_name: 'Acme' }],
    requests: [],
  };
  const accounts = {
    [ADMIN.email]: { password: 'admin-pass', user: ADMIN },
    [REGULAR.email]: { password: 'user-pass', user: REGULAR },
  };

  await page.route('**/api/login', async (route) => {
    const body = route.request().postDataJSON();
    state.requests.push({ method: 'POST', path: '/login', body });
    const account = accounts[body.email];
    if (!account || account.password !== body.password) {
      return json(route, 401, { error: 'Invalid email or password' });
    }
    return json(route, 200, { access_token: `token-${account.user.role}`, user: account.user });
  });

  await page.route('**/api/admin/dashboard', (route) => {
    if (sessionExpired) return json(route, 401, { msg: 'Token has expired' });
    return json(route, 200, { organizations: state.organizations, users: state.users });
  });

  await page.route('**/api/admin/users', async (route) => {
    const body = route.request().postDataJSON();
    state.requests.push({ method: route.request().method(), path: '/admin/users', body });
    const org = state.organizations.find((o) => o.id === body.org_id);
    const created = { id: `u-${state.users.length + 1}`, email: body.email, role: body.role, org_id: body.org_id, org_name: org?.name };
    state.users.push(created);
    return json(route, 201, { user: created });
  });

  await page.route('**/api/admin/users/*', async (route) => {
    const request = route.request();
    state.requests.push({ method: request.method(), path: new URL(request.url()).pathname.replace('/api', '') });
    if (request.method() === 'DELETE') {
      const id = new URL(request.url()).pathname.split('/').pop();
      state.users = state.users.filter((u) => u.id !== id);
    }
    return json(route, 200, {});
  });

  // Regular users land on the assistant, which asks for a LiveKit token. The
  // mock answers with an error so no real LiveKit connection is attempted.
  await page.route('**/api/getToken**', (route) => json(route, 503, { error: 'Voice service is unavailable' }));

  return state;
}

export async function login(page, email, password) {
  await page.goto('/');
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Password').fill(password);
  await page.getByRole('button', { name: 'Sign in' }).click();
}
