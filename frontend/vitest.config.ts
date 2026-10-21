import {defineConfig} from 'vitest/config';
export default defineConfig({
  define:{__EDUSYNC_BUILD__:JSON.stringify('component-test')},
  test:{include:['tests/**/*.test.{ts,tsx}']},
});
