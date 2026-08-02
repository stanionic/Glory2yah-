/**
 * Bus d'événements simplifié (en mémoire) simulant Apache Kafka pour la démo.
 * En production : remplacer par un vrai broker Kafka, avec topics par domaine
 * (wallet.*, loan.*, escrow.*) et consumer groups par microservice.
 */

const EventEmitter = require("events");
const bus = new EventEmitter();
const log = [];

function publish(topic, payload) {
  const event = { topic, payload, timestamp: new Date().toISOString() };
  log.push(event);
  bus.emit(topic, payload);
  bus.emit("*", event);
  return event;
}

function subscribe(topic, handler) {
  bus.on(topic, handler);
}

function getEventLog() {
  return log;
}

module.exports = { publish, subscribe, getEventLog, bus };
