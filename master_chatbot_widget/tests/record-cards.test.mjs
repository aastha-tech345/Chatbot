import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { extractRecords, RecordCards } from '../dist/RecordCards.js';

const render = (data, content = 'I completed `search` and found 1 record: {"id":1}') => renderToStaticMarkup(createElement(RecordCards, { message: { id: '1', role: 'assistant', content, timestamp: new Date(), data } }));
test('unwraps patient pagination and nested data envelopes', () => {
  const patients = [{ id: 21, first_name: 'Aastha', last_name: 'Gupta', patient_code: 'PAT-21' }];
  assert.deepEqual(extractRecords([{ total: 11, page: 1, patients }]), patients);
  assert.deepEqual(extractRecords([{ data: { results: patients } }]), patients);
  assert.match(render([{ patients }]), /Aastha Gupta/);
});
test('keeps product nested images within a single card and suppresses raw fallback JSON', () => {
  const product = { id: 'p1', name: 'Sunglasses', price: 699, images: [{ url: 'https://example.com/glasses.jpg' }] };
  assert.equal(extractRecords([product]).length, 1);
  const html = render([product]);
  assert.match(html, /Sunglasses/);
  assert.match(html, /glasses.jpg/);
  assert.match(html, /699/);
  assert.doesNotMatch(html, /I completed|&quot;id&quot;/);
});
test('generic records show safe details without secrets or unsafe image URLs', () => {
  const html = render([{ title: 'Appointment', status: 'Scheduled', token: 'secret-value', image_url: 'javascript:alert(1)', notes: '<script>alert(1)</script>' }]);
  assert.match(html, /Appointment/);
  assert.match(html, /View details/);
  assert.doesNotMatch(html, /secret-value|javascript:|<script>/);
});
test('empty lists and normal conversation retain assistant text', () => {
  assert.deepEqual(extractRecords([{ patients: [], total: 0 }]), []);
  assert.equal(render([], 'No patients found.'), 'No patients found.');
});
test('long lists initially show five cards with a show more control', () => {
  const html = render(Array.from({ length: 12 }, (_, id) => ({ id, name: `Item ${id}` })));
  assert.equal((html.match(/<article/g) || []).length, 5);
  assert.match(html, /7 remaining/);
});

test('ShopNest media and default variant prices render without boilerplate', () => {
  const html = render([{ id:'p1', name:'Watch', media:[{media_url:'https://example.com/watch.jpg'}], variants:[{price:2499,currency:'INR',is_default:true}] }], 'Here is the result:');
  assert.match(html, /watch.jpg/);
  assert.match(html, /2,499/);
  assert.doesNotMatch(html, /Here is the result/);
});

test('order cards expose cancel action when eligibility allows it', () => {
  const html = render([{ id: 'o-123', order_id: 'o-123', status: 'Confirmed', can_cancel: true, total: 1200 }], 'Your orders');
  assert.match(html, /Cancel Order/i);
  assert.match(html, /data-action-type="cancel"/i);
  assert.match(html, /data-order-id="o-123"/i);
});

test('delivered products show return, refund and replacement options', () => {
  const html = render([{ id: 'item-44', order_id: 'o-123', order_item_id: 'item-44', product_id: 'p-44', name: 'Wireless Earbuds', status: 'Delivered', delivery_status: 'DELIVERED', can_return: true, can_refund: true, can_replace: true }], 'Here is your delivered product');
  assert.match(html, /Return/i);
  assert.match(html, /Refund/i);
  assert.match(html, /Replacement/i);
});

test('product cards include a bug checkout action', () => {
  const html = render([{ id: 'p-99', name: 'Noise Cancelling Headphones', price: 3999, variants: [{ price: 3999, currency: 'INR' }] }], 'Here are the products');
  assert.match(html, /Bug/i);
  assert.match(html, /data-action-type="bug"/i);
});
