// Keep Vite in this process: no shell process tree to terminate on Windows.
import {createServer,preview} from 'vite';
import {spawn} from 'node:child_process';
import {createRequire} from 'node:module';
const require=createRequire(import.meta.url);
const port=Number(process.env.EDUSYNC_TEST_PORT||5181);
const production=process.env.EDUSYNC_TEST_BUILD==='1';
const server=production?await preview({preview:{host:'127.0.0.1',port,strictPort:true}}):await createServer({server:{host:'127.0.0.1',port,strictPort:true}});
if(!production)await server.listen();
try{
  const cli=require.resolve('@playwright/test/cli');
  const child=spawn(process.execPath,[cli,'test',...process.argv.slice(2)],{stdio:'inherit',env:{...process.env,EDUSYNC_TEST_EXTERNAL_SERVER:'1'}});
  process.exitCode=await new Promise((resolve,reject)=>{child.on('error',reject);child.on('exit',code=>resolve(code??1));});
}finally{if(production)await new Promise(resolve=>server.httpServer.close(resolve));else await server.close();}
