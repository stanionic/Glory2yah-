// src/validators.js
// Validation manuelle simple (sans dépendance lourde). Remplaçable par zod/yup/joi
// si déjà utilisé ailleurs dans Glory2YahPub — gardez la cohérence avec l'existant.

const ROLE_LABELS = ['pasteur','responsable','membre','jeune','groupe_de_priere','organisation','autre'];
const PARTICIPATION_TYPES = ['individuelle','eglise','mission','organisation','ligue_de_pasteurs','groupe_de_priere'];
const ORG_TYPES = ['eglise','mission','organisation','ligue_de_pasteurs','groupe_de_priere'];

function isNonEmptyString(v, max = 255) {
  return typeof v === 'string' && v.trim().length > 0 && v.trim().length <= max;
}

function isValidPhone(v) {
  // Accepte formats internationaux simples : +509XXXXXXXX, chiffres/espaces/tirets
  return typeof v === 'string' && /^[+0-9()\-.\s]{7,20}$/.test(v.trim());
}

function isValidEmail(v) {
  if (!v) return true; // email optionnel
  return typeof v === 'string' && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v.trim());
}

function sanitizeText(v, max = 2000) {
  if (typeof v !== 'string') return null;
  // Retire balises HTML basiques pour éviter le stockage de markup non désiré.
  return v.replace(/<[^>]*>/g, '').trim().slice(0, max);
}

function validateParticipant(body) {
  const errors = [];
  if (!isNonEmptyString(body.full_name)) errors.push('full_name invalide');
  if (!isValidPhone(body.phone)) errors.push('phone invalide');
  if (!isValidEmail(body.email)) errors.push('email invalide');
  if (body.role_label && !ROLE_LABELS.includes(body.role_label)) errors.push('role_label invalide');
  if (body.participation_type && !PARTICIPATION_TYPES.includes(body.participation_type)) errors.push('participation_type invalide');
  // Honeypot anti-spam : champ caché côté formulaire, doit rester vide
  if (body.website) errors.push('spam détecté');
  return errors;
}

function validateOrganization(body) {
  const errors = [];
  if (!isNonEmptyString(body.org_name)) errors.push('org_name invalide');
  if (!ORG_TYPES.includes(body.org_type)) errors.push('org_type invalide');
  if (!isNonEmptyString(body.contact_name)) errors.push('contact_name invalide');
  if (!isValidPhone(body.phone)) errors.push('phone invalide');
  if (!isValidEmail(body.email)) errors.push('email invalide');
  if (body.approx_participants && (!Number.isInteger(body.approx_participants) || body.approx_participants < 0)) {
    errors.push('approx_participants invalide');
  }
  if (body.website) errors.push('spam détecté');
  return errors;
}

module.exports = {
  validateParticipant,
  validateOrganization,
  sanitizeText,
  isValidPhone,
  isValidEmail,
};
