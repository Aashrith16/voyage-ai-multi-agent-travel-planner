import { useEffect, useState } from 'react'
import { Compass } from 'lucide-react'
import { markDestinationImageUnavailable, resolveDestinationImage, shouldShowDestinationPlaceholder } from '../lib/destinationImage'

export default function DestinationImage({ destination, children }) {
  const [imageState, setImageState] = useState({ destination: '', image: null, failed: false })

  useEffect(() => {
    let current = true
    resolveDestinationImage(destination).then(result => {
      if (current) setImageState({ destination, image: result, failed: false })
    })
    return () => { current = false }
  }, [destination])

  const image = imageState.destination === destination ? imageState.image : null
  const failed = imageState.destination === destination && imageState.failed
  const showPlaceholder = shouldShowDestinationPlaceholder(image, failed)
  return <div className={`saved-trip-image${showPlaceholder ? ' destination-image-placeholder' : ''}`} role="group" aria-label={`${destination || 'Trip'} destination image`}>
    {!showPlaceholder && <img
      className="saved-trip-photo"
      src={image.imageUrl}
      alt={`${image.destinationTitle} destination photograph`}
      loading="lazy"
      onError={() => {
        markDestinationImageUnavailable(destination)
        setImageState(current => current.destination === destination ? { ...current, failed: true } : current)
      }}
    />}
    {showPlaceholder && <div className="destination-placeholder-art" aria-hidden="true"><Compass size={34} strokeWidth={1.5} /></div>}
    {children}
    {!showPlaceholder && <div className="destination-photo-credit">
      <a href={image.sourceUrl} target="_blank" rel="noopener noreferrer" title={`Image source: ${image.destinationTitle}`}>Photo: {image.artist}</a>
      {' | '}
      <a href={image.licenseUrl} target="_blank" rel="noopener noreferrer" title="Image license">{image.license}</a>
    </div>}
  </div>
}
