import {defineConfig} from '@playwright/test';
const port=process.env.EDUSYNC_TEST_PORT||'5181';
const output=process.env.EDUSYNC_TEST_OUTPUT||'test-results';
export default defineConfig({
  testDir:'./browser-tests', fullyParallel:false, retries:0,
  outputDir:output, reporter:[['list'],['json',{outputFile:`${output}/browser-results.json`}]],
  use:{baseURL:`http://127.0.0.1:${port}`,headless:true,
    ...(process.env.EDUSYNC_TEST_BROWSER?{channel:process.env.EDUSYNC_TEST_BROWSER as 'msedge'}:{}),
    ...(process.env.EDUSYNC_TEST_EXECUTABLE?{launchOptions:{executablePath:process.env.EDUSYNC_TEST_EXECUTABLE}}:{}), screenshot:'only-on-failure'},
  webServer:process.env.EDUSYNC_TEST_EXTERNAL_SERVER?undefined:{command:`npm run dev -- --host 127.0.0.1 --port ${port} --strictPort`,url:`http://127.0.0.1:${port}`,reuseExistingServer:!process.env.CI},
});
