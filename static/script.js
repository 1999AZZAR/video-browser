document.addEventListener('DOMContentLoaded', function() {
    const fileStructure = document.getElementById('file-structure');
    const searchInput = document.getElementById('search-input');
    const searchButton = document.getElementById('search-button');
    const gridViewBtn = document.getElementById('grid-view-btn');
    const listViewBtn = document.getElementById('list-view-btn');
    let allItems = [];
    let currentView = 'grid';
    let currentFolder = null;

    // Add loading indicator
    const loadingIndicator = document.createElement('div');
    loadingIndicator.id = 'loading-indicator';
    loadingIndicator.textContent = 'Loading...';
    fileStructure.appendChild(loadingIndicator);

    fetch('/api/structure')
        .then(response => response.json())
        .then(data => {
            // Remove loading indicator
            fileStructure.removeChild(loadingIndicator);

            allItems = data;
            renderItems(getRootItems());
        })
        .catch(error => {
            console.error('Error:', error);
            // Update loading indicator to show error
            loadingIndicator.textContent = 'Error loading directory structure. Please try again.';
        });

    searchButton.addEventListener('click', performSearch);
    searchInput.addEventListener('keyup', function(event) {
        if (event.key === 'Enter') {
            performSearch();
        }
    });

    gridViewBtn.addEventListener('click', () => setView('grid'));
    listViewBtn.addEventListener('click', () => setView('list'));

    function setView(view) {
        currentView = view;
        fileStructure.className = `${view}-view`;
        gridViewBtn.classList.toggle('active', view === 'grid');
        listViewBtn.classList.toggle('active', view === 'list');
        renderItems(currentFolder ? getFolderItems(currentFolder) : getRootItems());
        // Add back button if in a folder
        if (currentFolder) {
            addBackButton();
        }
    }

    function performSearch() {
        const searchTerm = searchInput.value.toLowerCase();
        const filteredItems = allItems.filter(item =>
            item.name.toLowerCase().includes(searchTerm)
        );
        renderItems(filteredItems);
    }

    function renderItems(items) {
        fileStructure.innerHTML = '';
        items.forEach(item => {
            const itemElement = document.createElement('div');
            itemElement.className = currentView === 'grid' ? 'grid-item' : 'list-item';
            const iconPath = item.type === 'folder' ? '/static/image/folder.png' : '/static/image/video.png';
            itemElement.innerHTML = `
                <img src="${iconPath}" alt="${item.type} icon">
                <span>${item.name}</span>
            `;
            if (item.type === 'folder') {
                itemElement.addEventListener('click', () => openFolder(item));
            } else {
                itemElement.addEventListener('click', () => playVideo(item));
            }
            fileStructure.appendChild(itemElement);
        });
    }

    function getRootItems() {
        return allItems.filter(item => item.path.split('/').length === 1);
    }

    function getFolderItems(folder) {
        const folderPath = folder.path + '/';
        return allItems.filter(item => item.path.startsWith(folderPath) && item.path.split('/').length === folder.path.split('/').length + 1);
    }

    let folderHistory = [];

    function openFolder(folder) {
        folderHistory.push(currentFolder);
        currentFolder = folder;
        renderItems(getFolderItems(folder));
        updateNavigationButtons();
    }

    function addNavigationButtons() {
        if (!document.getElementById('navigation-buttons')) {
            const navigationButtons = document.createElement('div');
            navigationButtons.id = 'navigation-buttons';

            const backButton = document.createElement('button');
            backButton.id = 'back-button';
            backButton.innerHTML = `<img src="/static/image/back.png" alt="Back"> Back`;
            backButton.addEventListener('click', goBack);

            const homeButton = document.createElement('button');
            homeButton.id = 'home-button';
            homeButton.innerHTML = `<img src="/static/image/home.png" alt="Home"> Home`;
            homeButton.addEventListener('click', goHome);

            navigationButtons.appendChild(backButton);
            navigationButtons.appendChild(homeButton);
            fileStructure.insertBefore(navigationButtons, fileStructure.firstChild);
        }
    }

    function updateNavigationButtons() {
        addNavigationButtons();
        const navigationButtons = document.getElementById('navigation-buttons');

        if (currentFolder === null && folderHistory.length === 0) {
            // We're at the root, hide the entire navigation
            navigationButtons.style.display = 'none';
        } else {
            navigationButtons.style.display = 'flex';
            const backButton = document.getElementById('back-button');
            backButton.style.display = folderHistory.length > 0 ? 'inline-flex' : 'none';

            const homeButton = document.getElementById('home-button');
            homeButton.style.display = currentFolder !== null ? 'inline-flex' : 'none';
        }
    }

    function goBack() {
        if (folderHistory.length > 0) {
            currentFolder = folderHistory.pop();
            if (currentFolder) {
                renderItems(getFolderItems(currentFolder));
            } else {
                renderItems(getRootItems());
            }
        } else {
            renderItems(getRootItems());
        }
        updateNavigationButtons();
    }

    function goHome() {
        folderHistory = [];
        currentFolder = null;
        renderItems(getRootItems());
        updateNavigationButtons();
    }

    function playVideo(video) {
        window.location.href = `/play/${video.path}`;
    }

});

function fetchRelatedVideos(folderPath) {
    console.log('Fetching related videos for folder:', folderPath);
    fetch(`/api/related-videos?folder=${encodeURIComponent(folderPath)}`)
        .then(response => response.json())
        .then(data => {
            console.log('Received related videos data:', data);
            renderRelatedVideos(data);
        })
        .catch(error => {
            console.error('Error fetching related videos:', error);
            const relatedVideosContainer = document.getElementById('related-videos');
            relatedVideosContainer.innerHTML = '<p>Error loading related videos. Please try again.</p>';
        });
}

function renderRelatedVideos(videos) {
    const relatedVideosContainer = document.getElementById('related-videos');
    relatedVideosContainer.innerHTML = '';
    console.log('Rendering related videos:', videos);
    if (videos.length === 0) {
        relatedVideosContainer.innerHTML = '<p>No related videos found.</p>';
        return;
    }
    videos.forEach(video => {
        const videoElement = document.createElement('div');
        videoElement.className = relatedCurrentView === 'grid' ? 'grid-item' : 'list-item';
        videoElement.innerHTML = `
            <img src="/static/image/video.png" alt="Video thumbnail">
            <span>${video.name}</span>
        `;
        videoElement.addEventListener('click', () => {
            console.log('Clicked on related video:', video.path);
            window.location.href = `/play/${encodeURIComponent(video.path)}`;
        });
        relatedVideosContainer.appendChild(videoElement);
    });
}

// Make sure this part is included in your video.html or adjust accordingly
document.addEventListener('DOMContentLoaded', function() {
    const videoPlayer = document.getElementById('video-player');
    const relatedGridViewBtn = document.getElementById('related-grid-view-btn');
    const relatedListViewBtn = document.getElementById('related-list-view-btn');
    let relatedCurrentView = 'grid';
    let folderPath = '';

    relatedGridViewBtn.addEventListener('click', () => setRelatedView('grid'));
    relatedListViewBtn.addEventListener('click', () => setRelatedView('list'));

    function setRelatedView(view) {
        relatedCurrentView = view;
        const relatedVideosContainer = document.getElementById('related-videos');
        relatedVideosContainer.className = `${view}-view`;
        relatedGridViewBtn.classList.toggle('active', view === 'grid');
        relatedListViewBtn.classList.toggle('active', view === 'list');
        fetchRelatedVideos(folderPath);
    }
        relatedCurrentView = view;
        const relatedVideosContainer = document.getElementById('related-videos');
        relatedVideosContainer.className = `${view}-view`;
        relatedGridViewBtn.classList.toggle('active', view === 'grid');
        relatedListViewBtn.classList.toggle('active', view === 'list');
        fetchRelatedVideos(folderPath);
    }
    if (videoPlayer) {
        const currentVideoPath = videoPlayer.querySelector('source').src;
        console.log('Current video path:', currentVideoPath);
        folderPath = currentVideoPath.split('/').slice(0, -1).join('/');
        console.log('Extracted folder path:', folderPath);
        fetchRelatedVideos(folderPath);
    }
        const currentVideoPath = videoPlayer.querySelector('source').src;
        console.log('Current video path:', currentVideoPath);
        const folderPath = currentVideoPath.split('/').slice(0, -1).join('/');
        console.log('Extracted folder path:', folderPath);
        fetchRelatedVideos(folderPath);
    }
});
