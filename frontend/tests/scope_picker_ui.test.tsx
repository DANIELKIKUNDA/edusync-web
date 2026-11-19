// @vitest-environment jsdom
import React from 'react';
import {it,expect,vi,afterEach} from 'vitest';
import {render,screen,within,cleanup} from '@testing-library/react';
import EffectifsPage from '../src/effectifs';
import {StudentDirectoryPro} from '../src/schooling_kit';
import {getStructureSelector} from '../src/api';
vi.mock('../src/platform/live',()=>({useLive:()=>{}}));
vi.mock('../src/api',async original=>({...await original<any>(),getStructureSelector:vi.fn(async()=>({school_wide:false,sections:[{id:'s',code:'SECONDAIRE',label:'Secondaire'}],classes:[],options:[]})),getEffectifsOverview:vi.fn(async()=>null),getEffectifsCounts:vi.fn(async()=>({items:[],total:null})),listOptionSelector:vi.fn(async()=>[]),listYearSelector:vi.fn(async()=>[])}));
afterEach(()=>{cleanup();vi.clearAllMocks()});
it('a secondary head sees only the Secondary scope and it is selected automatically',async()=>{
 render(<EffectifsPage token="t" permissions={['headcounts.read','headcounts.by_class.read']} schoolName="Test"/>);
 const group=screen.getByRole('group',{name:'Périmètre'});
 const secondary=await within(group).findByRole('button',{name:'Secondaire'});
 expect(secondary.getAttribute('aria-pressed')).toBe('true');
 expect(within(group).queryByRole('button',{name:'Primaire'})).toBeNull();
 expect(within(group).queryByRole('button',{name:'Toute l’école'})).toBeNull();
 expect(getStructureSelector).toHaveBeenCalledWith('t','headcounts.by_class.read',undefined);
});
it('a school-wide grant keeps the whole-school choice',async()=>{
 vi.mocked(getStructureSelector).mockResolvedValueOnce({school_wide:true,sections:[{id:'p',code:'PRIMAIRE',label:'Primaire'},{id:'s',code:'SECONDAIRE',label:'Secondaire'}],classes:[],options:[]} as any);
 render(<EffectifsPage token="school" permissions={['headcounts.read','headcounts.by_class.read']} schoolName="Test"/>);
 const group=screen.getByRole('group',{name:'Périmètre'});
 expect(await within(group).findByRole('button',{name:'Toute l’école'})).toBeTruthy();
 expect(within(group).getByRole('button',{name:'Primaire'})).toBeTruthy();
});
it('the pupil directory removes the unnecessary all-sections choice for one visible section',async()=>{
 const setFilters=vi.fn();
 render(<StudentDirectoryPro token="t" schoolName="Test" classes={[{id:'c',section_id:'s',section_code:'SECONDAIRE',section_label:'Secondaire',label:'7EB'}] as any} filters={{}} setFilters={setFilters} students={[]} loading={false} can={()=>false} onSelect={()=>{}} page={0} hasMore={false} onPage={()=>{}}/>);
 expect(within(screen.getByLabelText('Section')).getAllByRole('option').map(x=>x.textContent)).toEqual(['Secondaire']);
 expect(setFilters).toHaveBeenCalledWith(expect.objectContaining({section_id:'s'}));
});
