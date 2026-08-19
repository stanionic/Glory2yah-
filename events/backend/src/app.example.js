// src/app.example.js
// EXEMPLE d'intégration — à fusionner dans votre fichier app.js/server.js existant.
// Ne créez pas une deuxième app Express : ajoutez simplement ces lignes.

const express = require('express');
const app = express();

app.use(express.json());

// Vos middlewares existants (auth, cors, etc.) restent en place.
// const requireAdminAuth = require('./middleware/auth'); // <- votre middleware existant

app.use('/api/events', require('./routes.events.public'));
app.use('/api/admin/events', /* requireAdminAuth, */ require('./routes.events.admin'));

module.exports = app;
