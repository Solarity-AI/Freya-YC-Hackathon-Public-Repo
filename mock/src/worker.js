// Cloudflare Worker entry: the generic engine (engine.js) driven by the three data files that
// tools/mockgen/make_config.py writes next to this folder. Do not edit by hand for a case: regenerate the data.
//
// Ledger storage is a SQLite-backed Durable Object (binding LEDGER_DO, class Ledger): the stateless Worker forwards
// every request that touches a customer's ledger to the DO named after that customer id, which runs the same engine
// against its transactional ctx.storage. One writer per customer, so verify -> get_account is never stale.
import { DurableObject } from "cloudflare:workers";
import CONFIG from "../config.json";
import OPENAPI from "../openapi.json";
import CUSTOMERS from "../customers.json";
import { createMock } from "./engine.js";

const mock = createMock({ config: CONFIG, openapi: OPENAPI, customers: CUSTOMERS });

export class Ledger extends DurableObject {
  async fetch(request) {
    return mock.fetch(request, { ADMIN_TOKEN: this.env.ADMIN_TOKEN, __store: this.ctx.storage });
  }
}

export default {
  async fetch(request, env, ctx) {
    return mock.fetch(request, env, ctx);
  },
};
