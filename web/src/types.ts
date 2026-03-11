export interface CardStat {
  name: string;
  section: string;
  deck_count: number;
  total_decks: number;
  total_copies: number;
  inclusion_rate: number;
  avg_copies: number;
}

export interface Legend {
  name: string;
  slug: string;
  image: string;
  deck_count: number;
  sections: Record<string, CardStat[]>;
}

export interface AppData {
  legends: Legend[];
}
