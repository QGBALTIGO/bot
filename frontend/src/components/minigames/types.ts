export interface MinigameState {
  energy: number;
  max_energy: number;
  last_energy_recharge: string | null;
}

export interface SessionData {
  start_time: number;
  cards?: {
    id: string;
    img_url: string;
    name: string;
  }[];
  prize?: {
    type: string;
    label: string;
    amount?: number;
  };
  prize_index?: number;
}

export interface Reward {
  shards: number;
  xp: number;
  character?: {
    id: string;
    name: string;
    anime: string;
    rarity: string;
    img_url: string;
  } | null;
}
