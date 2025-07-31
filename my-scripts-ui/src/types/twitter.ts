export interface TwitterPhoto {
  id: string;
  url: string;
  thumbnailUrl: string;
  highResUrl?: string;
  width: number;
  height: number;
  caption?: string;
  likes?: number;
  retweets?: number;
  comments?: number;
  publishedAt: string;
  tweetId: string;
  isVideo: boolean;
  videoUrl?: string;
}

export interface TwitterProfile {
  id: string;
  username: string;
  displayName: string;
  bio?: string;
  profileImageUrl: string;
  bannerUrl?: string;
  followersCount: number;
  followingCount: number;
  tweetsCount: number;
  isVerified: boolean;
  isPrivate: boolean;
  joinDate: string;
  website?: string;
  location?: string;
}

export interface TwitterScrapingResult {
  profile: TwitterProfile;
  photos: TwitterPhoto[];
  hasMore: boolean;
  nextCursor?: string;
}

export interface TwitterScrapingProgress {
  current: number;
  total: number;
  percentage: number;
  status: 'loading' | 'scraping' | 'completed' | 'error';
  message: string;
}

export interface TwitterScrapingError {
  code: 'PROFILE_NOT_FOUND' | 'PRIVATE_PROFILE' | 'RATE_LIMITED' | 'NETWORK_ERROR' | 'AUTH_REQUIRED' | 'UNKNOWN_ERROR';
  message: string;
  details?: any;
}

export interface TwitterAuthResponse {
  accessToken: string;
  userId: string;
  expiresIn: number;
}

export interface TwitterApiCredentials {
  apiKey: string;
  apiSecret: string;
  accessToken: string;
  accessTokenSecret: string;
}