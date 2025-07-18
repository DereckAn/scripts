export interface InstagramPhoto {
  id: string;
  url: string;
  thumbnailUrl: string;
  caption?: string;
  likes?: number;
  comments?: number;
  timestamp?: string;
  isVideo: boolean;
  dimensions?: {
    width: number;
    height: number;
  };
}

export interface InstagramProfile {
  username: string;
  fullName?: string;
  bio?: string;
  profilePicUrl?: string;
  followersCount?: number;
  followingCount?: number;
  postsCount?: number;
  isVerified?: boolean;
  isPrivate: boolean;
  externalUrl?: string;
}

export interface InstagramScrapingResult {
  profile: InstagramProfile;
  photos: InstagramPhoto[];
  totalCount: number;
  hasMore: boolean;
  nextCursor?: string;
}

export interface InstagramScrapingProgress {
  current: number;
  total: number;
  percentage: number;
  status: 'loading' | 'scraping' | 'completed' | 'error';
  message: string;
}

export interface InstagramScrapingError {
  code: 'PROFILE_NOT_FOUND' | 'PRIVATE_PROFILE' | 'RATE_LIMITED' | 'NETWORK_ERROR' | 'UNKNOWN_ERROR';
  message: string;
  details?: string;
}