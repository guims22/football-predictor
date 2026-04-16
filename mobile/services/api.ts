import axios from "axios";

const BASE_URL = "http://10.11.245.116:8000";

export const api = axios.create({
  baseURL: BASE_URL,
  timeout: 20000,
});

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
}

export interface Prediction {
  home_win: number;
  draw: number;
  away_win: number;
  predicted_score: string;
  confidence: number;
}

export interface QuickPrediction {
  match_id: number;
  home_team: string;
  away_team: string;
  competition: string;
  prediction: Prediction;
  tip: string;
}

export interface FullPrediction extends QuickPrediction {
  home_form: TeamForm;
  away_form: TeamForm;
  h2h: { home_wins: number; draws: number; away_wins: number };
  analysis: string;
}

export interface Competition {
  id: number;
  code: string;
  name: string;
  area: string;
  emblem: string;
  type: string;
}

// ─── API Calls ────────────────────────────────────────────────────────────────

export const getMatchesToday = () =>
  api.get<{ matches: Match[] }>("/matches/today");

export const getUpcomingMatches = (days = 7) =>
  api.get<{ matches: Match[] }>(`/matches/upcoming?days=${days}`);

export const getCompetitionMatches = (code: string) =>
  api.get<{ matches: Match[] }>(`/matches/competition/${code}`);

export const getQuickPrediction = (params: {
  match_id: number;
  home_team_id: number;
  away_team_id: number;
  home_team_name: string;
  away_team_name: string;
  competition?: string;
}) => api.get<QuickPrediction>("/predictions/quick", { params });

export const getFullPrediction = (params: {
  match_id: number;
  home_team_id: number;
  away_team_id: number;
  home_team_name: string;
  away_team_name: string;
  competition?: string;
}) => api.get<FullPrediction>("/predictions/full", { params });

export const getCompetitions = () =>
  api.get<{ competitions: Competition[]; count: number }>("/leagues");

export const getStandings = (code: string) =>
  api.get(`/leagues/${code}/standings`);
