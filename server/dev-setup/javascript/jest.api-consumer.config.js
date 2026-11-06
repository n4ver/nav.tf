/** @type {import('jest').Config} */
module.exports = {
  testEnvironment: 'node',
  rootDir: '../../../api-consumer',
  testMatch: ['**/tests/**/*.test.js'],
  collectCoverageFrom: ['src/**/*.js', '!src/index.js'],
  coverageDirectory: '../server/dev-setup/javascript/coverage/api-consumer',
  coverageReporters: ['text', 'html', 'lcov'],
};
