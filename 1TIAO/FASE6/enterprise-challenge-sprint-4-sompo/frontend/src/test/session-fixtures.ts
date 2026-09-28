import type { Principal } from '../lib/api-contracts'

const adminFixture: Principal = {
  id: '88888888-8888-4888-8888-888888888888',
  worker_id: '000001',
  role: 'ADMIN',
  fleet_id: null,
}

const insurerFixture: Principal = {
  id: '55555555-5555-4555-8555-555555555555',
  worker_id: '000123',
  role: 'INSURER',
  fleet_id: null,
}

const inspectorFixture: Principal = {
  id: '66666666-6666-4666-8666-666666666666',
  worker_id: '000456',
  role: 'INSPECTOR',
  fleet_id: null,
}

const managerFixture: Principal = {
  id: '77777777-7777-4777-8777-777777777777',
  worker_id: '000789',
  role: 'FLEET_MANAGER',
  fleet_id: '11111111-1111-4111-8111-111111111111',
}

export { adminFixture, insurerFixture, inspectorFixture, managerFixture }
