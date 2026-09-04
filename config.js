// Deployment configuration.
//
// Point this at your own API Gateway stage URL after deploying the backend
// (see template.yaml / README.md). Keeping it in its own file means the
// rest of the frontend never needs to change between environments.
const APP_CONFIG = {
  API_BASE_URL: "https://eqpd6y86k1.execute-api.eu-north-1.amazonaws.com/prod",
};
