import { Command } from 'commander';
import { StoryHealClient } from '../client.js';
import { resolveOutput, resolveServer } from '../config.js';
import { printError, printResult } from '../output.js';

function makeClient(globals: Record<string, string>) {
  return new StoryHealClient({ server: resolveServer(globals.server), token: globals.token });
}

function action(
  handler: (client: StoryHealClient, opts: Record<string, string>) => Promise<unknown>,
) {
  return async (opts: Record<string, string>, cmd: Command) => {
    const globals = cmd.parent!.parent!.opts();
    const format = resolveOutput(globals.output);
    try {
      printResult(await handler(makeClient(globals), opts), format);
    } catch (error) {
      printError(error, format);
    }
  };
}

export function registerOperationsCommands(parent: Command): void {
  const ops = parent.command('ops').description('Operate the Storyblok self-healing loop');

  ops.command('analytics').description('Show proof-of-usefulness metrics')
    .action(action((client) => client.get('/v1/knowledge-ops/analytics')));
  ops.command('findings').description('List detected knowledge failures')
    .action(action((client) => client.get('/v1/knowledge-ops/findings')));
  ops.command('proposals').description('List human-review proposals')
    .option('--status <status>', 'Filter by proposal status')
    .action(action((client, opts) => client.get(`/v1/knowledge-ops/proposals${opts.status ? `?status=${encodeURIComponent(opts.status)}` : ''}`)));
  ops.command('analyze').requiredOption('--session <id>', 'Closed visitor session UUID')
    .description('Queue immediate knowledge analysis')
    .action(action((client, opts) => client.post('/v1/knowledge-ops/analyze', { session_id: opts.session })));
  ops.command('approve').argument('<proposal-id>').option('--reason <text>', 'Review note')
    .description('Approve and publish after server-side gate rechecks')
    .action(async (proposalId: string, opts: Record<string, string>, cmd: Command) => {
      const globals = cmd.parent!.parent!.opts();
      const format = resolveOutput(globals.output);
      try {
        printResult(await makeClient(globals).post(`/v1/knowledge-ops/proposals/${proposalId}/approve`, { reason: opts.reason }), format);
      } catch (error) { printError(error, format); }
    });
  ops.command('reject').argument('<proposal-id>').requiredOption('--reason <text>', 'Mandatory rejection reason')
    .description('Reject a Storyblok draft proposal')
    .action(async (proposalId: string, opts: Record<string, string>, cmd: Command) => {
      const globals = cmd.parent!.parent!.opts();
      const format = resolveOutput(globals.output);
      try {
        printResult(await makeClient(globals).post(`/v1/knowledge-ops/proposals/${proposalId}/reject`, { reason: opts.reason }), format);
      } catch (error) { printError(error, format); }
    });
  ops.command('storyblok-test').description('Test separated Storyblok credentials')
    .action(action((client) => client.post('/v1/storyblok/test', {})));
  ops.command('storyblok-provision').description('Idempotently provision StoryHeal components and workflow')
    .action(action((client) => client.post('/v1/storyblok/provision', {})));
  ops.command('storyblok-sync').description('Refresh all published Storyblok content into RAG')
    .action(action((client) => client.post('/v1/storyblok/sync', {})));
}

