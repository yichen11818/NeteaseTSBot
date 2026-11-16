# TSBot Music - Frontend

A modern Vue.js frontend for the TSBot music player with comprehensive music management features.

## Features

- 🎵 **Modern Music Player**: Full-featured player with playback controls, progress bar, and volume control
- 🎤 **Lyrics Display**: Real-time synchronized lyrics display
- 📱 **Responsive Design**: Mobile-first design that works on all devices
- 🎨 **Beautiful UI**: Modern interface built with TailwindCSS and Lucide icons
- 🔍 **Music Search**: Search and discover music from NetEase Cloud Music
- 📋 **Playlist Management**: Drag-and-drop playlist organization
- ❤️ **Favorites**: Manage your liked songs
- 📚 **Music Library**: Browse your playlists and music collection
- 📈 **Play History**: Track your listening history
- ⚙️ **Settings**: Configure NetEase Cloud Music cookies

## Technology Stack

- **Vue 3** - Progressive JavaScript framework
- **TypeScript** - Type-safe development
- **TailwindCSS** - Utility-first CSS framework
- **Lucide Icons** - Beautiful, customizable icons
- **Vue Router** - Client-side routing
- **Vite** - Fast build tool and dev server

## Installation

### Prerequisites

- Node.js 16+ and npm
- TSBot backend server running

### Setup

1. **Install dependencies**:
   ```bash
   npm install
   ```

2. **Configure environment** (optional):
   The recommended default is same-origin `/api`, which works with the repository's Vite and Docker proxy setup:
   ```env
   VITE_API_BASE=/api
   ```
   If your backend is on a completely different origin and you do not use the built-in proxy, set it to an absolute URL instead.

3. **Development server**:
   ```bash
   npm run dev
   ```
   The app will be available at `http://localhost:5173` and proxies `/api` to the backend target derived from `TSBOT_HOST` / `TSBOT_PORT` (or `TSBOT_WEB_API_PROXY_TARGET`). If you access the dev server through a remote domain, also set `TSBOT_WEB_ALLOWED_HOSTS`.

4. **Build for production**:
   ```bash
   npm run build
   npm run preview -- --host 127.0.0.1 --port 8080
   ```

5. **Repository production helper**:
   ```bash
   ../run-web.sh
   ```

## Project Structure

Multi-server deployments serve a public `servers.json` catalog alongside the Web app. The normal build includes an empty catalog for single-server mode; `scripts/multi_server.py` configures Nginx to serve the generated catalog instead. Routes under `/s/<id>/` use `/api/servers/<id>/` for every API call and managed asset. Server switching loads a new document, so timers, CSRF state and pending UI work remain tied to their original server. Tabs can manage different servers independently. Catalog or startup errors remain visible and offer a server selector; unknown IDs never fall back to another bot.

Deployment, per-server credentials, data paths and migration are maintained in [HOWTOSTART.md](../HOWTOSTART.md#一个项目连接多个-teamspeak-服务器). The multi-server Web build uses the same-origin gateway rather than `VITE_API_BASE`. Existing development and preview scripts still serve single-server mode unless placed behind that gateway.

```
web/
├── src/
│   ├── components/          # Reusable components
│   │   ├── MusicPlayer.vue  # Main music player component
│   │   ├── LyricsDisplay.vue # Lyrics display component
│   │   └── PlaylistView.vue # Enhanced playlist component
│   ├── views/              # Page components
│   │   ├── SearchView.vue  # Music search page
│   │   ├── QueueView.vue   # Playback queue
│   │   ├── LikesView.vue   # Liked songs
│   │   ├── PlaylistsView.vue # User playlists
│   │   ├── HistoryView.vue # Play history
│   │   └── CookieView.vue  # Settings page
│   ├── api.ts             # API client functions
│   ├── router.ts          # Vue Router configuration
│   ├── style.css          # Global styles and Tailwind
│   ├── App.vue            # Main app component
│   └── main.ts            # App entry point
├── public/                # Static assets
├── index.html            # HTML template
├── package.json          # Dependencies and scripts
├── tailwind.config.js    # Tailwind configuration
├── postcss.config.js     # PostCSS configuration
└── vite.config.ts        # Vite configuration
```

## Key Components

### MusicPlayer
The main music player component featuring:
- Play/pause, skip controls
- Progress bar with seeking
- Volume control
- Current track display with artwork
- Like/unlike functionality

### LyricsDisplay
Real-time lyrics display with:
- Auto-scrolling synchronized lyrics
- Highlighted current line
- Smooth animations
- Error handling for missing lyrics

### PlaylistView
Enhanced playlist management with:
- Drag-and-drop reordering
- Multi-select operations
- Search and filtering
- Batch operations

## API Integration

The frontend communicates with the TSBot backend through REST APIs:

- `GET /queue` - Get current playback queue
- `POST /queue/netease` - Add NetEase song to queue
- `GET /search` - Search for music
- `GET /voice/status` - Get player status
- `POST /voice/play` - Control playback
- `GET /netease/playlists` - Get user playlists
- `GET /netease/likes` - Get liked songs

## Configuration

### NetEase Cloud Music Integration
To use NetEase Cloud Music features:

1. Go to the Settings page (`/cookie`)
2. Enter your NetEase Cloud Music cookie
3. The cookie is stored locally and used for:
   - Accessing your playlists
   - Viewing liked songs
   - Getting high-quality audio streams

### Customization

The app uses TailwindCSS for styling. You can customize:

- Colors in `tailwind.config.js`
- Component styles in `src/style.css`
- Layout and spacing throughout the components

## Development

### Available Scripts

- `npm run dev` - Start development server
- `npm run build` - Build for production
- `npm run preview` - Preview production build

### Code Style

- TypeScript for type safety
- Vue 3 Composition API
- Consistent component structure
- Responsive design patterns
- Accessibility considerations

## Browser Support

- Chrome/Chromium 88+
- Firefox 78+
- Safari 14+
- Edge 88+

## Troubleshooting

### Common Issues

1. **API Connection Failed**
   - Ensure backend server is running
   - Recommended default is `VITE_API_BASE=/api`
   - If you bypass same-origin proxying, point `VITE_API_BASE` or `TSBOT_WEB_API_PROXY_TARGET` at the correct backend
   - If you access Vite through a domain, whitelist it via `TSBOT_WEB_ALLOWED_HOSTS`

2. **NetEase Features Not Working**
   - Verify cookie is correctly set in Settings
   - Check cookie format and validity
   - Ensure backend has NetEase integration enabled

3. **Styling Issues**
   - Run `npm run build` to ensure Tailwind is processed
   - Check browser console for CSS errors
   - Verify PostCSS configuration

## Contributing

1. Follow the existing code style
2. Add TypeScript types for new features
3. Test on multiple screen sizes
4. Ensure accessibility standards
5. Update documentation for new features
