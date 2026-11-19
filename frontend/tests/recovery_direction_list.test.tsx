// @vitest-environment jsdom
import React from 'react';
import {it,expect,vi,afterEach} from 'vitest';
import {render,screen,cleanup} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import RecoveryDirection from '../src/recovery_direction';
vi.mock('../src/api',()=>({recoveryFees:vi.fn(async()=>({items:[]})),recoveryDirectionReport:vi.fn(async()=>({title:'Octobre',as_of_label:'19 novembre',total:{concerned:2,in_order:0,not_in_order:2},sections:[],analysis:{without_contact:0},exempted_counts:{ARRIVAL:0,EXEMPTION:0},unpaid:[{enrollment_id:'1',student_name:'Élève Alpha',matricule:'A1',section_label:'Secondaire',class_label:'7EB',missing:['Octobre'],contact_name:'Parent Alpha',contact_phone:'0991234567',remaining:100},{enrollment_id:'2',student_name:'Élève Beta',matricule:'B1',section_label:'Primaire',class_label:'1P',missing:['Octobre'],contact_name:'Parent Beta',contact_phone:'',remaining:200}]})),recoveryDirectionReportPdf:vi.fn()}));
afterEach(cleanup);
it('shows named debtors and contacts, searches without accents, and filters by authorized section',async()=>{
 const user=userEvent.setup();render(<RecoveryDirection token="test" can={()=>false} yearId="year" currency="CDF" live={0}/>);
 await screen.findByText('Élève Alpha');expect(screen.getByRole('link',{name:'0991234567'}).getAttribute('href')).toBe('tel:0991234567');
 await user.type(screen.getByRole('searchbox'),'eleve alpha');expect(screen.queryByText('Élève Beta')).toBeNull();
 await user.clear(screen.getByRole('searchbox'));await user.selectOptions(screen.getByLabelText('Section des élèves à relancer'),'Primaire');expect(screen.queryByText('Élève Alpha')).toBeNull();expect(screen.getByText('Élève Beta')).toBeTruthy();
 expect(screen.queryByRole('button',{name:'Produire le rapport PDF'})).toBeNull();
});
