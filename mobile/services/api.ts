import axios from "axios";
import Constants from "expo-constants";

/**
 * URL du backend.
 *
 * AVANT : "http://10.11.245.116:8000" ecrit en dur. Cette IP est celle du PC
 * de developpement sur un reseau local precis : des que le PC change de reseau
 * (ou qu'on deploie sur Railway), l'app ne joint plus rien et il faut recompiler.
 *
 * MAINTENANT, par ordre de priorite :
 *   1. EXPO_PUBLIC_API_URL (fichier .env a la racine de mobile/)
 *   2. extra.apiUrl dans app.json
 *   3. l'IP du poste qui sert le bundle Expo, deduite automatiquement
 *   4. http://localhost:8000
 */
function resolveBaseUrl(): string {
  const fromEnv = process.env.EXPO_PUBLIC_API_URL;
  if (fromEnv) return fromEnv;

  const fromConfig = Constants.expoConfig?.extra?.apiUrl as string | undefined;
  if (fromConfig) return fromConfig;

  // hostUri ressemble a "192.168.1.42:8081" quand Expo sert le bundle
  const hostUri =
    Constants.expoConfig?.hostUri ??
    (Constants.expoGoConfig as { debuggerHost?: string } | undefined)?.debuggerHost;
  if (hostUri) {
    const host = hostUri.split(":")[0];
    if (host) return `http://${host}:8000`;
  }

  return "http://localhost:8000";
}

export const BASE_URL = resolveBaseUrl();

/**
 * Cle d'acces partagee avec le backend.
 *
 * Une fois l'API deployee publiquement, elle est joignable par n'importe qui :
 * sans cette cle, un inconnu pourrait declencher des appels Claude factures sur
 * le compte du proprietaire. Elle est injectee a la compilation depuis
 * EXPO_PUBLIC_API_KEY, ou lue depuis extra.apiKey.
 *
 * Ce n'est pas un secret fort -- il est extractible de l'APK -- mais cela suffit
 * a bloquer les robots qui scannent les domaines Railway.
 */
const API_KEY =
  process.env.EXPO_PUBLIC_API_KEY ??
  ((Constants.expoConfig?.extra?.apiKey as string | undefined) || "");

export const BASE_URL_IS_REMOTE = /^https:\/\//i.test(BASE_URL);

export const api = axios.create({
  baseURL: BASE_URL,
  timeout: 30000, // l'analyse Claude peut prendre une vingtaine de secondes
  headers: API_KEY ? { "X-API-Key": API_KEY } : undefined,
});

/** Message d'erreur lisible : l'app affichait "Request failed with status code 500". */
export function describeError(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail = (error.response?.data as { detail?: string } | undefined)?.detail;
    if (detail) return detail;
    if (error.code === "ECONNABORTED") return "Le serveur met trop de temps a repondre.";
    if (!error.response) return `Backend injoignable (${BASE_URL}). Est-il demarre ?`;
    if (error.response.status === 401)
      return "Cle d'acces refusee par le serveur. L'app doit etre reconstruite avec la bonne cle.";
    return `Erreur ${error.response.status}`;
  }
  return "Erreur inconnue";
}

// ─── Types ───────────────────────────────────────────────────────────────────

export interface Match {
  id: number;
  utcDate: string;
  status: string;
  matchday?: number;
  homeTeam: { id: number; name: string; shortName: string; crest: string };
  awayTeam: { id: number; name: string; shortName: string; crest: string };
  score: {
    fullTime: { home: number | null; away: number | null };
    halfTime: { home: number | null; away: number | null };
  };
  competition: { id: number; name: string; code: string; emblem: string };
}

export interface TeamForm {
  wins: number;
  draws: number;
  losses: number;
  avg_goals_scored: number;
  avg_goals_conceded: number;
  form_score: number;
  played: number;
  clean_sheets: number;
  cs_rate: number;
  xg_attack: number;
  xg_defense: number;
}

export interface ValueBet {
  model_prob: number;
  market_prob: number;
  edge: number;
  expected_value: number;
  value_bet: boolean;
}

export interface Prediction {
  home_win: number;
  draw: number;
  away_win: number;
  predicted_score: string;
  confidence: number;
  home_xg: number;
  away_xg: number;
  btts: number;
  over_1_5: number;
  over_2_5: number;
  over_3_5: number;
  method: string;
  model_loaded: boolean;
  odds?: { home: number; draw: number; away: number };
  value_analysis?: Record<string, ValueBet>;
}

export interface QuickPrediction {
  match_id: number;
  home_team: string;
  away_team: string;
  competition: string;
  prediction: Prediction;
  tip: string | null;
  odds_available: boolean;
}

export interface FullPrediction extends QuickPrediction {
  home_form: TeamForm;
  away_form: TeamForm;
  home_form_home: TeamForm;
  away_form_away: TeamForm;
  h2h: { home_wins: number; draws: number; away_wins: number; total: number };
  standings: { home_position: number | null; away_position: number | null };
  analysis: string | null;
}

export interface Competition {
  id: number;
  code: string;
  name: string;
  area: string;
  emblem: string;
  type: string;
}

export interface Health {
  status: "ok" | "degraded";
  degraded: string[];
  api_keys: { claude: boolean; football_data: boolean; odds: boolean };
  model: { loaded: boolean; reason: string; accuracy: number | null };
}

/**
 * Parametres de prediction.
 * competition_code et match_date sont nouveaux : sans le code de ligue, le
 * backend ne pouvait ni recuperer les cotes ni le classement.
 */
export interface PredictionParams {
  match_id: number;
  home_team_id: number;
  away_team_id: number;
  home_team_name: string;
  away_team_name: string;
  competition?: string;
  competition_code?: string;
  match_date?: string;
}

/** Construit les parametres depuis un match : evite d'oublier le code de ligue. */
export const paramsFromMatch = (m: Match): PredictionParams => ({
  match_id: m.id,
  home_team_id: m.homeTeam.id,
  away_team_id: m.awayTeam.id,
  home_team_name: m.homeTeam.name,
  away_team_name: m.awayTeam.name,
  competition: m.competition?.name ?? "",
  competition_code: m.competition?.code ?? "",
  match_date: m.utcDate,
});

// ─── Appels API ──────────────────────────────────────────────────────────────

export const getHealth = () => api.get<Health>("/health");

export const getMatchesToday = () => api.get<{ matches: Match[] }>("/matches/today");

export const getUpcomingMatches = (days = 7) =>
  api.get<{ matches: Match[] }>("/matches/upcoming", { params: { days } });

export const getCompetitionMatches = (code: string) =>
  api.get<{ matches: Match[] }>(`/matches/competition/${code}`);

export const getQuickPrediction = (params: PredictionParams) =>
  api.get<QuickPrediction>("/predictions/quick", { params });

export const getFullPrediction = (params: PredictionParams) =>
  api.get<FullPrediction>("/predictions/full", { params });

export const getCompetitions = () =>
  api.get<{ competitions: Competition[]; count: number }>("/leagues/");

export const getStandings = (code: string) => api.get(`/leagues/${code}/standings`);

export const askAnalyst = (question: string, history: { role: "user" | "assistant"; content: string }[] = []) =>
  api.post<{ response: string }>("/analysis/chat", { question, history });
