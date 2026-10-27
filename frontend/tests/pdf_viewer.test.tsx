// @vitest-environment jsdom
import React from 'react';
import {afterEach,expect,it} from 'vitest';
import {cleanup,render,screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {PdfPreviewHost} from '../src/platform/pdf_viewer';
import {previewPdfUrl} from '../src/document_io';

afterEach(()=>cleanup());

it('keeps PDF preview inside EduSync and exposes explicit print/download/external actions', async()=>{
  render(<PdfPreviewHost/>);
  previewPdfUrl('https://example.test/report.pdf','Rapport financier journalier');
  expect(await screen.findByRole('dialog',{name:'Rapport financier journalier'})).toBeTruthy();
  expect(screen.getByText('Aperçu dans EduSync')).toBeTruthy();
  expect(screen.getByRole('button',{name:/Imprimer/})).toBeTruthy();
  expect(screen.getByRole('link',{name:/Télécharger/})).toBeTruthy();
  expect(screen.getByRole('link',{name:/Ouvrir séparément/})).toBeTruthy();
  await userEvent.click(screen.getByRole('button',{name:'Retour'}));
  expect(screen.queryByRole('dialog')).toBeNull();
});
