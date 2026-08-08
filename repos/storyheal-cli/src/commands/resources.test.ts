import { describe, it, expect, vi } from 'vitest';
import { providerList, providerCreate, providerTest, providerEnable, providerDisable } from './provider.js';
import { knowledgeList, knowledgeGet, knowledgeCreate, knowledgeSearch, knowledgeDelete } from './knowledge.js';
import { platformList, platformGet } from './platform.js';
import { tagList, tagCreate, tagDelete } from './tag.js';
import type { StoryHealClient } from '../client.js';

function mockClient() {
  return {
    get: vi.fn().mockResolvedValue({}),
    post: vi.fn().mockResolvedValue({}),
    put: vi.fn().mockResolvedValue({}),
    patch: vi.fn().mockResolvedValue({}),
    delete: vi.fn().mockResolvedValue(undefined),
  } as unknown as StoryHealClient & {
    get: ReturnType<typeof vi.fn>;
    post: ReturnType<typeof vi.fn>;
    delete: ReturnType<typeof vi.fn>;
  };
}

describe('provider commands', () => {
  it('providerList should GET /v1/ai/providers', async () => {
    const client = mockClient();
    await providerList(client);
    expect(client.get).toHaveBeenCalledWith('/v1/ai/providers');
  });

  it('providerCreate should POST /v1/ai/providers', async () => {
    const client = mockClient();
    await providerCreate(client, {
      name: 'OpenAI',
      provider_type: 'openai',
      api_key: 'sk-test',
      api_base: 'https://api.openai.com',
    });
    expect(client.post).toHaveBeenCalledWith('/v1/ai/providers', {
      name: 'OpenAI',
      provider_type: 'openai',
      api_key: 'sk-test',
      api_base: 'https://api.openai.com',
    });
  });

  it('providerTest should POST /v1/ai/providers/:id/test', async () => {
    const client = mockClient();
    await providerTest(client, 'prov-1');
    expect(client.post).toHaveBeenCalledWith('/v1/ai/providers/prov-1/test', {});
  });

  it('providerEnable should POST /v1/ai/providers/:id/enable', async () => {
    const client = mockClient();
    await providerEnable(client, 'prov-1');
    expect(client.post).toHaveBeenCalledWith('/v1/ai/providers/prov-1/enable', {});
  });

  it('providerDisable should POST /v1/ai/providers/:id/disable', async () => {
    const client = mockClient();
    await providerDisable(client, 'prov-1');
    expect(client.post).toHaveBeenCalledWith('/v1/ai/providers/prov-1/disable', {});
  });
});

describe('knowledge commands', () => {
  it('knowledgeList should GET /v1/rag/collections with pagination', async () => {
    const client = mockClient();
    await knowledgeList(client, { limit: 10, offset: 5 });
    expect(client.get).toHaveBeenCalledWith('/v1/rag/collections?limit=10&offset=5');
  });

  it('knowledgeGet should GET /v1/rag/collections/:id', async () => {
    const client = mockClient();
    await knowledgeGet(client, 'col-1');
    expect(client.get).toHaveBeenCalledWith('/v1/rag/collections/col-1');
  });

  it('knowledgeCreate should POST /v1/rag/collections', async () => {
    const client = mockClient();
    await knowledgeCreate(client, { display_name: 'FAQ', description: 'FAQ collection' });
    expect(client.post).toHaveBeenCalledWith('/v1/rag/collections', {
      display_name: 'FAQ',
      description: 'FAQ collection',
    });
  });

  it('knowledgeSearch should POST search with query', async () => {
    const client = mockClient();
    await knowledgeSearch(client, 'col-1', { query: 'how to return', limit: 5 });
    expect(client.post).toHaveBeenCalledWith('/v1/rag/collections/col-1/documents/search', {
      query: 'how to return',
      limit: 5,
    });
  });

  it('knowledgeDelete should DELETE /v1/rag/collections/:id', async () => {
    const client = mockClient();
    await knowledgeDelete(client, 'col-1');
    expect(client.delete).toHaveBeenCalledWith('/v1/rag/collections/col-1');
  });
});

describe('platform commands', () => {
  it('platformList should GET /v1/platforms', async () => {
    const client = mockClient();
    await platformList(client);
    expect(client.get).toHaveBeenCalledWith('/v1/platforms');
  });

  it('platformGet should GET /v1/platforms/:id', async () => {
    const client = mockClient();
    await platformGet(client, 'plat-1');
    expect(client.get).toHaveBeenCalledWith('/v1/platforms/plat-1');
  });
});

describe('tag commands', () => {
  it('tagList should GET /v1/tags with category filter', async () => {
    const client = mockClient();
    await tagList(client, { category: 'visitor' });
    expect(client.get).toHaveBeenCalledWith('/v1/tags?category=visitor');
  });

  it('tagList should GET /v1/tags without filter', async () => {
    const client = mockClient();
    await tagList(client);
    expect(client.get).toHaveBeenCalledWith('/v1/tags');
  });

  it('tagCreate should POST /v1/tags', async () => {
    const client = mockClient();
    await tagCreate(client, { name: 'VIP', category: 'visitor', color: '#ff0000' });
    expect(client.post).toHaveBeenCalledWith('/v1/tags', {
      name: 'VIP',
      category: 'visitor',
      color: '#ff0000',
    });
  });

  it('tagDelete should DELETE /v1/tags/:id', async () => {
    const client = mockClient();
    await tagDelete(client, 'tag-1');
    expect(client.delete).toHaveBeenCalledWith('/v1/tags/tag-1');
  });
});
