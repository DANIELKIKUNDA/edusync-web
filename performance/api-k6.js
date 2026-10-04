import http from 'k6/http';import {check,sleep} from 'k6';
export const options={scenarios:{steady:{executor:'ramping-vus',startVUs:1,stages:[{duration:'30s',target:25},{duration:'60s',target:50},{duration:'30s',target:0}]},spike:{executor:'constant-arrival-rate',rate:30,timeUnit:'1s',duration:'45s',preAllocatedVUs:20,maxVUs:100}},thresholds:{http_req_failed:['rate<0.01'],http_req_duration:['p(95)<800','p(99)<1500']}};
const BASE=__ENV.BASE_URL||'http://localhost:8000';export default function(){const r=http.get(`${BASE}/health`);check(r,{'health 200':x=>x.status===200});sleep(0.2)}
